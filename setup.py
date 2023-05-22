from setuptools import setup

# with open('README.rst') as readme_file:
#     readme = readme_file.read()

# with open('HISTORY.rst') as history_file:
#     history = history_file.read()

with open("requirements.txt") as requires_file:
    requirements = requires_file.read().split("\n")

requirements = [requirement for requirement in requirements if not ("+" in requirement)]
    
test_requirements = [
    # TODO: put package test requirements here
]

setup(
    name='asimov',
    use_scm_version={"local_scheme": "no-local-version"},
    setup_requires=['setuptools_scm'],
    description="""A Python package for managing and interacting with data analysis jobs.""",
    #long_description=readme + '\n\n' + history,
    author="Daniel Williams",
    author_email='daniel.williams@ligo.org',
    url='https://git.ligo.org/asimov/asimov',
    packages=['asimov'],
    package_dir={'asimov': 'asimov'},
    entry_points={
        'console_scripts': [
            'olivaw=asimov.olivaw:olivaw',
            'asimov=asimov.olivaw:olivaw',
            'locutus=asimov.locutus:cli'
        ]
    },
    include_package_data=True,
    install_requires=requirements,
    license="MIT license",
    zip_safe=True,
    keywords='pe, ligo, asimov',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Astronomy',
        'Topic :: Scientific/Engineering :: Information Analysis',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Operating System :: POSIX :: Linux',
        
    ],
    test_suite='tests',
    tests_require=test_requirements,
)
