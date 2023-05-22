0.4.0
=====

Breaking changes
----------------

This release of asimov is not backwards compatible with releases from the v0.3 series, and has multiple breaking changes.

Major New Features
-------------------

Projects
""""""""

This version of asimov represents a major update compared to the previously released versions of asimov.
In the past asimov has relied on gitlab issue trackers in order to organise a project.
In this version we introduce infrastructure within asimov to enable management of much smaller projects as well as those asimov was initially intended for.
Projects can now be created in a user's home directory and used to organise and automate multiple runs.

Pipeline interface improvements
"""""""""""""""""""""""""""""""

We've made a serious effort in this version to improve the interface between asimov and various gravitational wave analysis pipelines, including Bayeswave, bilby, and lalinference.
We've made it much easier to use other pipelines with asimov too, which can now be implemented as plugins without requiring upstream changes to the asimov codebase.

Reporting improvements
""""""""""""""""""""""

We've introduced a number of new features to the report pages which are created by asimov in order to give a more useful overview of all of the analyses which are being run.

Command-line interface
""""""""""""""""""""""

Asimov now has a cleaner, and more consistent command line interface, which has been renamed ``asimov``.
When we started work on the project we weren't sure how asimov would be used, but we've come to the conclusion that having everything named consistently is for the best.

Blueprint files
"""""""""""""""

Setting up events and analyses in asimov requires a large amount of information.
To assist with this, asimov is now able to read-in this information in yaml-format files which we call "blueprints".
A curated collection of these for the events included in the GWTC catalogues, and the analyses used for those catalogues are available from https://git.ligo.org/asimov/data.


Review status
-------------

This release has been reviewed for use in parameter estimation analyses of the LVK.
+ Review statements can be found in the ``REVIEW.rst`` file in this repository.
+ Full information regarding the review is available `in this wiki page<https://git.ligo.org/pe/O4/asimov-review/-/wikis/Asimov-version-O4>`_.

Getting ``asimov v0.4.0``
-------------------------

pypi
""""
You can install this preview directly from pypi using pip:
``pip install --upgrade asimov==v0.4.0``

git
"""
You can clone this repository and install from source by running

::

   git clone git@git.ligo.org:asimov/asimov.git
   git checkout v0.4.0
   pip install .

What's next?
------------

You can find the most up to date O4 development roadmap `on the project wiki<https://git.ligo.org/asimov/asimov/-/wikis/o4-roadmap>`.
