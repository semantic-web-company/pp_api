from setuptools import setup

with open('requirements.txt', 'r') as f:
    requirements = f.read().splitlines()
requirements = [x for x in requirements
                if ((len(x.strip()) > 0)
                     and (x[0] != '-')       # -e URL?
                     and ("+" not in x)      # ??
                     and (x[:2] != "# ")) ]  # comment lines
requirements = [x.replace("python-", "python_") for x in requirements]
dependencies = ["https://github.com/Project-PROFIT/nif.git@origin/master#egg=nif"]

setup(
    name='pp_api',
    version='18.1.0',
    description='Library for accessing PoolParty APIs',
    packages=['pp_api', 'pp_api.models'],
    license='MIT',
    dependency_links=dependencies,
    install_requires=requirements,
)
