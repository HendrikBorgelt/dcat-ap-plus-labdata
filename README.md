<a href="https://github.com/dalito/linkml-project-copier"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/copier-org/copier/master/img/badge/badge-grayscale-inverted-border-teal.json" alt="Copier Badge" style="max-width:100%;"/></a>

# dcat-ap-plus-labdata

A dcat-ap-plus extension intended for chemical labdata and chemical experiemnts, which consist of synthesis setps.

## Documentation Website

[https://HendrikBorgelt.github.io/dcat-ap-plus-labdata](https://HendrikBorgelt.github.io/dcat-ap-plus-labdata)

## Repository Structure

* [docs/](docs/) - mkdocs-managed documentation
  * [elements/](docs/elements/) - generated schema documentation
* [examples/](examples/) - Examples of using the schema
* [project/](project/) - project files (these files are auto-generated, do not edit)
* [src/](src/) - source files (edit these)
  * [dcat_p_lab](src/dcat_p_lab)
    * [schema/](src/dcat_p_lab/schema) -- LinkML schema
      (edit this)
    * [datamodel/](src/dcat_p_lab/datamodel) -- generated
      Python datamodel
* [tests/](tests/) - Python tests
  * [data/](tests/data) - Example data

## Developer Tools

There are several pre-defined command-recipes available.
They are written for the command runner [just](https://github.com/casey/just/). To list all pre-defined commands, run `just` or `just --list`.
```
Available recipes:

    gen-python  # Generate the Python data models (dataclasses & pydantic)

    [deployment]
    deploy      # Deploy documentation site to Github Pages

    [model development]
    gen-doc     # Generate md documentation for the schema
    gen-project # Generate project files including Python data model
    lint        # Run linting
    site        # (Re-)Generate project and documentation locally
    test        # Run all tests
    testdoc     # Build docs and run test server

    [project management]
    clean       # Clean all generated files
    install     # Install project dependencies
    setup       # Initialize a new project (use this for projects not yet under version control)
    update      # Updates project template and LinkML package
```

### Testing
`just test`herby runs two important commands `uv run linkml-run-examples --input-formats json --input-formats yaml --output-formats json --output-formats yaml --counter-example-input-directory tests/data/invalid --input-directory tests/data/valid --output-directory examples/output --schema src/dcat_p_lab/schema/dcat_p_lab.yaml > examples/output/README.md` and `uv run python -m pytest`  which runs the local testfile, see [tests/](tests/) - Python tests.

### Regenerating Project artefacts (python dataclasses, pydantic, json schema,...)

In order to update the schema it is allways recommended to only change the [src/](src/)[dcat_p_lab/](src/dcat_p_lab)[schema/](src/dcat_p_lab/schema) file, since you otherwise won't keep all artefacts synced. `just site`generates all artefacts for you, based on the settings in the [config](config.yaml) file and possibly the [justfile](justfile), which can modified on demand (be carefull, you might need to switch between `_`and `-` for the commands to run succesfully. For command options in the just file, look at the LinkML documentation of the individual generators and use the cli commands (e.g. https://linkml.io/linkml/generators/python.html).

## Credits

This project uses the template [linkml-project-copier](https://github.com/dalito/linkml-project-copier) published as [doi:10.5281/zenodo.15163584](https://doi.org/10.5281/zenodo.15163584).
