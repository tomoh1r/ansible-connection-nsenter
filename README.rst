==========================
ansible-connection-nsenter
==========================

It's implements ansible connector that enable you to connect to
a systemd-nspawn container.

Quick Start
===========

.. code-block:: console

   $ mkdir -p ~/.ansible/plugins/connection_plugins/
   $ curl https://raw.githubusercontent.com/jptomo/ansible-nsenter/master/nsenter.py -o ~/.ansible/plugins/connection_plugins/nsenter.py
