==========================
ansible-connection-nsenter
==========================

It's implements ansible connector that enable you to connect to
a systemd-nspawn container.

Description
===========

If connecting with nsenter, you need root privilege.

Quick Start
===========

tl;dr
-----

1. Create your container.
2. Add nsenter.py to your connectoin plugin's directory.
3. Specify your container on your Ansible Inventory.
4. Add nsenter connection settings and become settings to your Ansible playbook.
5. Run ansible-playbook command with K option.

You must create systemd-nspawn container under /var/lib/machines on Fedora 22.
And then, you must start container with ``# machinectl start <container_name>``.

If you finish steps below, you can see this directory structure.

::

  $ tree
  .
  ├── connection_plugins
  │   ├── nsenter.py
  ├── hosts
  └── playbook.yml

1. Create connection_plugin directory under Ansible directory.

.. code-block:: console

   $ cd /path/to/ansible/working/dir/
   $ mkdir connection_plugins
   $ curl https://raw.githubusercontent.com/jptomo/ansible-nsenter/master/nsenter.py -o connection_plugins/nsenter.py

2. Specify your container on your Ansible Inventory.

Like this

.. code-block:: console

   $ cat > hosts
   <container_name>

3. Add Ansible playbook.

Like this

.. code-block:: console

   $ cat > playbook.yml
   ---
   - hosts: all
     connection: nsenter
     become: yes
     tasks:
     - command: uname -a
       register: foo
     - debug: msg="{{foo}}"

You must specify ``connection: nsenter`` and ``become: yes``.

4. Run ansible-playbook command with K option.

The nsenter connection plusgin needs sudo permission, and if you run command
below, you shoud specify your current user's password.

.. code-block:: console

   $ ansible-playbook -i hosts playbook.yml -K
