# Terrain-atlas provenance and attribution

The 47-mask coordinate arrangement was transcribed and validated from the
3x3-minimal terrain example in the official Godot Engine documentation. The
relevant documentation is maintained by Juan Linietsky, Ariel Manzur, and the
Godot community and is licensed under Creative Commons Attribution 3.0
Unported, subject to the documentation repository's stated exceptions.

- Documentation: <https://docs.godotengine.org/en/latest/tutorials/2d/using_tilesets.html>
- Source repository: <https://github.com/godotengine/godot-docs>
- License: <https://creativecommons.org/licenses/by/3.0/>

FX Games distributes the coordinate lookup, the modified 12-by-4 paintover
template, and a redundant topology-reference crop with this attribution. The
template enlarges and annotates the Godot documentation terrain example with a
magenta exterior, cyan guide lattice, and locked checker placeholder. The image
provider receives the template first as the strict edit target and the original
grid crop second as topology-only visual instruction. Deterministic chroma-key
extraction owns alpha after validation; neither Godot-derived input becomes a
runtime asset. `tests/contract/test_packaged_resources.py` holds both packaged
copies to their attributed source digests, sizes and modes; FX Games does not
claim independent authorship of the source pixels.

The desert, frozen, and temperate images used during exploration remain
unreviewed external work products. They are not copied into this repository,
not canonical fixtures, not runtime assets, and not repository-approved media.
