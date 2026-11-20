# IASP Build

IASP Build uses Pandoc to build Markdown manuscripts with the Informative Authoring Semantics Profile. It includes the Lua filters, LaTeX templates, stylesheets, and vocabulary used by the manuscript builder.

Install from this checkout into the virtual environment used by your manuscript:

```sh
python3 -m pip install '/path/to/iasp-build'
```

The `kdp` extra adds Pillow for cover generation. Install Pandoc separately. PDF builds require XeLaTeX and its LaTeX packages. The builder can also use EPUBCheck for EPUB validation and qpdf for PDF optimization.

From a manuscript directory:

```sh
iasp-build epub
iasp-build --profile annex1 pdf-screen
iasp-build article-md articles/example.md
```

From elsewhere, pass `--project-root /path/to/manuscript`. A minimal manuscript needs `metadata.yaml`, `book-order.txt` listing its Markdown files, and `iasp-config.yaml` with `toc.enabled: false` if it has no generated table of contents. Named profiles in `build-profiles.json` can select an order file, additional metadata, cover artwork, and an output basename. Outputs go into the manuscript’s `build/` directory.

See the [pipeline guide](docs/Build%20Pipeline.md) and [semantic vocabulary](docs/Semantic%20Vocabulary.md) for details. Some examples use files from the original manuscript checkout.

To run the tests, install the `test` extra and run `python3 -m pytest`. The detached-manuscript integration test uses Pandoc.
