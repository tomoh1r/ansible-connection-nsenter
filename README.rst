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

.. code-block:: console

   $ sudo mkdir -p /etc/ansible/plugins/connection_plugins
   $ curl https://raw.githubusercontent.com/jptomo/ansible-nsenter/master/nsenter.py -o /etc/ansible/plugins/connection_plugins/nsenter.py

Then add `connection_plugins` to your `ansible.cfg` or else.
