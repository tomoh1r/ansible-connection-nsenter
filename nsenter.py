# (c) 2012, Michael DeHaan <michael.dehaan@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

import os
import fcntl
import select
import shlex
import subprocess
import traceback
from copy import deepcopy

from ansible import errors
from ansible import utils
from ansible.callbacks import vvv


class Connection(object):
    ''' nsenter connection '''

    def __init__(self, runner, host, *args, **kwargs):
        if os.geteuid() != 0:
            raise errors.AnsibleError(
                "nsenter connection requires running as root")

        self.runner = runner
        self.host = host

        if not bool(self._extract_var('Name')):
            raise errors.AnsibleError("invalid host name %s" % self.host)

        self.has_pipelining = False
        self.chroot = self._extract_var('RootDirectory')
        self.container_envs = self._get_container_env()

        # TODO: add su(needs tty), pbrun, pfexec
        self.become_methods_supported = ['sudo']

    def _get_container_env(self):
        '''return container env dict'''
        # get environ path
        env_path = '/proc/{}/environ'.format(self._extract_var('Leader'))

        # get container env separated by null char
        env_str = subprocess.check_output(shlex.split('cat ' + env_path))

        # split null and = char
        proc_envs = env_str.split('\0')
        proc_envs = dict([x.split('=') for x in proc_envs if x])
        return proc_envs

    def _extract_var(self, key):
        output = subprocess.check_output(['machinectl', 'show', self.host])
        for row in output.split('\n'):
            if key in row:
                return row.strip().lstrip(key + '=')

    def connect(self):
        ''' connect to the virtual host; nothing to do here '''

        vvv("THIS IS A CONTAINER DIR", host=self.chroot)

        return self

    def exec_command(self, cmd, tmp_path, become_user=None, sudoable=False,
                     executable='/bin/sh', in_data=None):
        ''' run a command on the virtual host '''
        # get params
        params = locals()
        del params['self']

        # if invalid arguments, then raise error.
        self._sanitize_command(**params)

        # if multiple command then split it
        if any(cmd.find(x) != -1 for x in ['&&', ';']):
            # split set env and actual command
            cmd_env, cmd = self._split_env(cmd)

            # calc symbol position
            pos_and = cmd.find('&&')
            pos_sc = cmd.find(';')  # semicolon
            conn_and = False
            conn_sc = False
            if (pos_and != -1 and
                    ((pos_sc != -1 and pos_and < pos_sc) or pos_sc == -1)):
                pos = pos_and
                post_pos = pos + 2
                conn_and = True
            else:
                pos = pos_sc
                post_pos = pos + 1
                conn_sc = True

            # parse cmd
            cmd_pre, cmd_post = cmd[:pos].strip(), cmd[post_pos:].strip()
            post_params = deepcopy(params)
            params['cmd'] = ' '.join([cmd_env, cmd_pre]).strip()
            post_params['cmd'] = ' '.join([cmd_env, cmd_post]).strip()

            # exec cmd
            result = self._exec_command(**params)
            if conn_and and result[0] == 0:
                return self._exec_command(**post_params)
            elif conn_sc:
                self._exec_command(**post_params)
                return result
            else:
                return result
        else:
            return self._exec_command(**params)

    def _sanitize_command(self, cmd, tmp_path, become_user, sudoable,
                          executable, in_data):
        '''this func sanitize arguments'''
        # su requires to be run from a terminal,
        # and therefore isn't supported here (yet?)
        if (sudoable and self.runner.become and
                self.runner.become_method not in self.become_methods_supported):
            raise errors.AnsibleError(
                "Internal Error: this module does not support running commands via %s"
                % self.runner.become_method)

        if in_data:
            raise errors.AnsibleError(
                "Internal Error: this module does not support optimized module pipelining")

    def _split_env(self, cmd):
        if any('=' in x for x in cmd.split(' ')):
            cmd_env = []
            for i, c in enumerate(cmd.split(' ')):
                if '=' in c:
                    cmd_env.append(c)
                else:
                    break
            return ' '.join(cmd_env), ' '.join(cmd.split(' ')[i:])
        else:
            return '', cmd

    def _exec_command(self, cmd, tmp_path, become_user, sudoable,
                      executable, in_data):
        '''run a command on the virtual host'''
        # replace container env to value
        for k, v in self.container_envs.items():
            key = '${}'.format(k)
            if key in cmd:
                cmd = cmd.replace(key, v)

        # decorate nsenter command
        nsenter = (
            'nsenter -m -u -i -n -p -t {}'
            .format(self._extract_var('Leader')))
        cmd_env, cmd_plan = self._split_env(cmd)
        cmd = ' '.join([cmd_env, nsenter, cmd_plan]).strip()

        if self.runner.become and sudoable:
            local_cmd, prompt, success_key = utils.make_become_cmd(
                cmd, become_user, executable, self.runner.become_method, '-H',
                self.runner.become_exe)
        else:
            if executable:
                local_cmd = executable.split() + ['-c', cmd]
            else:
                local_cmd = cmd
        executable = executable.split()[0] if executable else None

        vvv("EXEC %s" % (local_cmd), host=self.host)
        p = subprocess.Popen(local_cmd, shell=isinstance(local_cmd, basestring),
                             cwd=self.runner.basedir, executable=executable,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if self.runner.become and sudoable and self.runner.become_pass:
            fcntl.fcntl(p.stdout, fcntl.F_SETFL,
                        fcntl.fcntl(p.stdout, fcntl.F_GETFL) | os.O_NONBLOCK)
            fcntl.fcntl(p.stderr, fcntl.F_SETFL,
                        fcntl.fcntl(p.stderr, fcntl.F_GETFL) | os.O_NONBLOCK)
            become_output = ''
            while success_key not in become_output:

                if prompt and become_output.endswith(prompt):
                    break
                if utils.su_prompts.check_su_prompt(become_output):
                    break

                rfd, wfd, efd = select.select([p.stdout, p.stderr], [],
                                              [p.stdout, p.stderr], self.runner.timeout)
                if p.stdout in rfd:
                    chunk = p.stdout.read()
                elif p.stderr in rfd:
                    chunk = p.stderr.read()
                else:
                    stdout, stderr = p.communicate()
                    raise errors.AnsibleError(
                        'timeout waiting for %s password prompt:\n'
                        % self.runner.become_method + become_output)
                if not chunk:
                    stdout, stderr = p.communicate()
                    raise errors.AnsibleError(
                        '%s output closed while waiting for password prompt:\n'
                        % self.runner.become_method + become_output)
                become_output += chunk
            if success_key not in become_output:
                p.stdin.write(self.runner.become_pass + '\n')
            fcntl.fcntl(
                p.stdout, fcntl.F_SETFL,
                fcntl.fcntl(p.stdout, fcntl.F_GETFL) & ~os.O_NONBLOCK)
            fcntl.fcntl(
                p.stderr, fcntl.F_SETFL,
                fcntl.fcntl(p.stderr, fcntl.F_GETFL) & ~os.O_NONBLOCK)

        stdout, stderr = p.communicate()
        return (p.returncode, '', stdout, stderr)

    def put_file(self, in_path, out_path):
        ''' transfer a file from local to local '''
        vvv("PUT %s TO %s" % (in_path, out_path), host=self.host)
        out_path = os.path.join(self.chroot, out_path.lstrip('/'))
        if not os.path.exists(in_path):
            raise errors.AnsibleFileNotFound("file or module does not exist: %s" % in_path)
        try:
            subprocess.check_output(['cp', in_path, out_path])
        except Exception:
            traceback.print_exc()
            raise errors.AnsibleError("Some exceptions occurred.")

    def fetch_file(self, in_path, out_path):
        ''' fetch a file from local to local -- for copatibility '''
        vvv("FETCH %s TO %s" % (in_path, out_path), host=self.host)
        in_path = os.path.join(self.chroot, in_path.lstrip('/'))
        if not os.path.exists(out_path):
            raise errors.AnsibleFileNotFound("file or module does not exist: %s" % out_path)
        try:
            subprocess.check_output(['cp', in_path, out_path])
        except Exception:
            traceback.print_exc()
            raise errors.AnsibleError("Some exceptions occurred.")

    def close(self):
        ''' terminate the connection; nothing to do here '''
        pass
