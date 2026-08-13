=========================
Getting data from GraceDB
=========================

One of the major sources of data about gravitational wave events is `GraceDB`, a database of gravitational wave triggers which have been identified by one of many searches.

GraceDB clusters these triggers into "superevents", and normally we will want to request data from one of these superevents in order to start an analysis with `asimov`.

GraceDB support is LIGO/Virgo/KAGRA-specific, so it isn't part of asimov core. It's provided by the
optional `asimov-gracedb` plugin, which you'll need to install separately:

::
   $ pip install asimov-gracedb

Adding an event from the CLI
----------------------------

Once the plugin is installed you can directly download information about a trigger and create an event in the project using asimov's generic plugin-applicator interface.

If you want to pull information from non-public events you'll first need to ensure that you have a LIGO proxy set up.
The easiest way to do this as a normal user is just to run `ligo_proxy_init`:
::
   $ ligo_proxy_init isaac.asimov

and then provide your password to set up a proxy.
If you're working with publically available triggers then you can skip this step, and asimov will gather all of the publically available data which it can.

::
   $ asimov apply -p gracedb -e S200316bj

.. note::

   `GraceDB` will only provide a small amount of the total information which is needed to set up an analysis.
   You'll need things like default data settings before you can start an analysis.


