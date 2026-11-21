# Ubuntu source installation

Ubuntu runs Trial Cruncher from a source checkout. Install Python 3.12 or newer,
Git, and the matching Python virtual environment package. From the checkout:

```sh
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -e .
./trial-cruncher
```

If Ubuntu reports that `ensurepip` is missing, install its matching
`python3-venv` package. Qt WebEngine also needs the system graphics libraries
described in [testing](testing.md).

To update a clean checkout on the stable branch:

```sh
git switch main
git pull --ff-only
.build-venv/bin/python -m pip install -e .
./trial-cruncher
```

The source launcher uses the checkout's `.build-venv` and sets
`TRIAL_CRUNCHER_DISABLE_UPDATES=1`. Source sessions have no Velopack feed and the
application does not update the checkout automatically. Check `git status`
before pulling when local work is present.
