Writing tests for your productions
==================================

It's important that once productions have been made that they can be checked, and that their results can be verified.

To make this simple, asimov provides an extension to the built-in python ``unittest.TestCase``.
This provides access to all of the events and productions within an asimov project without the need to write additional boilerplate code.

You can then use tools from ``unittest`` such as asserts and ``subTest`` to construct your tests, whilst having full access to the information in the ledger.

Example: Checking prior files
-----------------------------

.. code-block:: python

   from asimov.testing import AsimovTest

   class TestBilbyPrior(AsimovTest):
       def test_component_chirp_mass(self):
	   """Verify the component chirp mass prior is correct."""

	   for event in self.events:
	       for production in event.productions:
		   if production.pipeline == "bilby":
		       with self.subTest(event=event.title, production=production.name):
			   repo = event.event_object.repository.directory
			   try:
			       with open(f"{repo}/analyses/{production.name}.prior", "r") as priorfile:
				   self.assertFalse("name='chirp_mass', minimum=7.932707, maximum=14.759644" in priorfile.read())
			   except FileNotFoundError:
			       pass


   if __name__ == '__main__':
       unittest.main()
