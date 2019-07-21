from setuptools import setup

setup(
    name='mallard-ducktype',
    version='1.0.2',
    description='Parse Ducktype files and convert them to Mallard.',
    packages=['mallard', 'mallard.ducktype', 'mallard.ducktype.extensions'],
    scripts=['bin/ducktype'],
    author='Shaun McCance',
    author_email='shaunm@gnome.org',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Customer Service',
        'Intended Audience :: Developers',
        'Intended Audience :: Other Audience',
        'Intended Audience :: System Administrators',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Documentation',
        'Topic :: Software Development :: Documentation',
        'Topic :: Text Processing :: Markup',
        'Topic :: Text Processing :: Markup :: XML',
        'License :: OSI Approved :: MIT License',
    ],
)
