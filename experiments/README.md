# Experiments Sandbox

This directory is for independent research, scratchpad scripts, and testing before moving code into the main application.

## Best Practices

1. **Environment Variables**: Scripts here should load the `.env` file from the root directory.
2. **Imports**: If you need to import from the `app` package, make sure your working directory is the project root, or add the project root to `PYTHONPATH`.
3. **Clean Up**: Feel free to create files here, but keep it organized.

## Running Experiments

To run a script while ensuring it can import from the `app` package:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python experiments/your_experiment.py
```

Or just run it from the root directory if using absolute imports from `app`.
