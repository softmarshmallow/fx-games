# Game concept style library

A prompt-writing map, not a schema or a closed menu. Use it to turn what the user describes into
words a model can see.

## Labels are candidates; observable facets are controls

A style label (`anime`, `painterly`, `retro`) is a word to search and talk with. What steers an
image is its observable facets: line, shading, palette, surface, proportion and depth. Many common
labels are not styles at all:

- `moe` is an affect: the feeling a character is meant to evoke.
- `shonen`, `shojo`, `seinen` and `josei` are publishing demographics.
- `webtoon` is a format: vertical-scroll digital comics.
- `chibi` and `SD` (super-deformed) are proportions.
- A cutscene still is a production role.

Build a direction from facets, in this order: lineage, character grammar, line, shading, palette
and value, surface, era technique, and then, chosen separately, the production role.

## Facet checklist

Select only the facets that materially define this concept:

- medium or production process: pixel raster, inked raster, cel illustration, gouache, watercolor
  and ink, painterly digital, pre-rendered 3D raster, or natural photography;
- character grammar and shape: grounded anatomy, head-heavy compact proportions, rounded geometry,
  angular silhouettes, mechanical modularity, or deliberately exaggerated action anatomy;
- line language: no contour, fine tapered ink, clean continuous ink, bold dark contour, broken dry
  brush, or dense hatching;
- shading and value: flat fills, one-band cel shadows, multi-band cel shadows, graphic shadow
  masses, continuous tonal modeling, or luminous rim separation;
- palette and light: bounded indexed palette, high-key pastel, muted earth pigments, jewel tones,
  saturated emissive accents, monochrome values, warm natural light, or theatrical contrast;
- surface: clean digital fill, paper grain, dry-brush opacity, screentone, analog cel texture,
  weathered material grain, or polished photographic texture;
- depth finish: flat graphic overlap, distinct painted planes, atmospheric value depth, volumetric
  haze, or physically plausible optical depth;
- camera and composition: keep this separate from rendering style;
- production role: cover key art, world concept, character study, mood painting, or UI
  exploration;
- content presentation: keep genre, violence, sexuality, wardrobe and exposure, and audience
  separate from rendering style. Any depicted person is unambiguously adult, and adult
  presentation is used only when the user asks for it.

## Axes

The first nine axes define a style. Affect modifies them. Role, content and composition are
context: they change what is drawn, not how.

| Axis | Decides | For example |
|---|---|---|
| Lineage | the tradition the look descends from | cel animation, inked comics, pixel-art games, editorial painting, woodblock print, photography |
| Medium | how the picture is made | pixel raster, cel illustration, gouache, watercolor and ink, pre-rendered 3D |
| Character grammar | proportion, faces, shape language | grounded anatomy, head-heavy compact, rounded, angular, modular |
| Line | contours and marks | none, fine tapered, clean continuous, bold dark, dry brush, hatching |
| Shading | how form is modeled | flat, one-band cel, multi-band cel, shadow masses, continuous tone |
| Palette and value | the colors and their range | indexed palette, high-key pastel, muted earth, jewel tones, monochrome |
| Light | where light comes from, and its quality | warm natural, overcast soft, theatrical contrast, emissive |
| Surface | the material of the picture | clean digital, paper grain, screentone, analog cel, weathered |
| Depth finish | how space recedes | flat overlap, painted planes, atmospheric value, volumetric haze, optical depth |
| Affect | the feeling the look carries | tender, playful, solemn, menacing, melancholic |
| Production role | what the image is for | cover key art, world concept, character study, mood painting |
| Content presentation | genre, violence, wardrobe, audience | everyday, heroic, grim, glamorous |
| Composition | camera and framing | side view, isometric, low angle, close portrait, wide establishing shot |

## Surface treatment

Decide surface on its own six axes, so texture never ages the whole picture by accident.

| Axis | Values |
|---|---|
| Substrate | clean digital raster, paper, canvas, cel acetate, printed stock |
| Texture scope | none, object-local (on materials only), global (over the whole image) |
| Material condition | pristine, worn, weathered, ruined |
| Microdetail density | sparse, moderate, dense |
| Color age | fresh, faded, yellowed |
| Global post-process | none, film grain, halftone screen, scanlines, vignette |

The default is a clean digital raster with object-local texture and no global aging. Add paper,
grain, fading or a post-process only when the concept asks for it.

## Keyword banks

Neutral words to pick from. None is a style alone.

- **Medium and process:** native-resolution pixel art, high-density pixel art, ordered dithering,
  inked raster, cel illustration, gouache, transparent watercolor, watercolor and ink, oil paint,
  colored pencil, charcoal, linocut, woodblock print, screen print, stencil duplicator print, paper
  cutout, painted clay, pre-rendered 3D raster, low-poly 3D, natural photography.
- **Line and mark-making:** no contour, fine tapered ink, clean uniform line, bold dark contour,
  colored line, visible construction lines, broken dry brush, cross-hatching, stippling, scratchy
  pen.
- **Shading and lighting:** flat fill, one-band cel shadow, two- or three-band cel shadow, graphic
  shadow masses, soft airbrushed gradient, continuous tonal modeling, chiaroscuro, rim light,
  bounce light, glowing emission.
- **Palette and value:** limited indexed palette, duotone, high-key pastel, low-key, muted earth
  pigments, jewel tones, complementary accent, monochrome values, sepia, neon emissive accents, one
  reserved accent color.
- **Surface and texture:** clean digital fill, paper grain, canvas weave, dry-brush opacity,
  screentone dots, halftone, stencil duplicator print misregistration, analog cel paint, film
  grain, weathered material grain.
- **Proportion, face and shape:** grounded proportions, heroic proportions, head-heavy compact
  proportions, rubber-hose limbs, large eyes with small mouths, simplified dot eyes, angular
  silhouettes, soft rounded shapes, blocky geometric forms.
- **Detail, depth and finish:** sparse detail, dense detail, detail falloff away from the focal
  point, flat graphic overlap, painted depth planes, atmospheric perspective, volumetric haze,
  shallow optical depth of field, matte finish, glossy finish.
- **Art history and design movements:** Art Nouveau, Art Deco, Bauhaus, Constructivism,
  Impressionism, Expressionism, Pop Art, mid-century modern illustration, psychedelic poster,
  illuminated manuscript, Baroque chiaroscuro, ukiyo-e woodblock print. A folk or heritage
  tradition belongs to living communities: describe its visible techniques, avoid sacred or
  protected motifs, and have someone who knows the tradition review the result before it is
  shared.

## Words that stay contextual

Some words bundle a mood, setting or market with a look: `whimsical`, `cozy`, `dark fantasy`,
`cyberpunk`, `steampunk`, `cottagecore`, `cinematic`, `premium`, `high quality`, `epic`. Never let
one stand for the style. Expand it into facets, or keep it in the subject.

Production roles are not styles either: standing character art (tachie), dialogue portrait,
cut-in, event illustration, key art, card illustration, loading screen, background painting, icon,
sprite sheet. Some role words are ambiguous:

- `sprite` names a runtime image, not a look;
- `CG`, in visual novels, names an event illustration, not 3D rendering;
- `key art` names a marketing role, not a finish;
- `SD` means super-deformed proportions, not a resolution.

## Never a style direction

- geography alone (`Japanese`, `Korean`, `Western`);
- a generic medium alone (`2D`, `anime`, `manga`);
- a platform tier (`mobile`, `AAA`, `indie`);
- a genre alone (`RPG`, `platformer`);
- an archetype alone (`knight`, `idol`);
- pose or camera words;
- quality filler (`masterpiece`, `best quality`, `trending`, `8k`);
- any named artist, studio, franchise, character or game, and any "in the style of".

## Starter bundles

Four complete directions, each a set of traits plus what to exclude. Use one as a base, or none.

- **Clean cel-shaded 2D illustration.** Crisp inked linework, flat cel-shaded color regions,
  discrete hard-edged shadow shapes, restrained gradients. Exclude photorealistic or
  semi-realistic rendering, 3D rendering, painterly realism, skin-pore detail, photographic depth
  of field and lens bokeh.
- **Photographic natural.** Real material texture, natural lighting, optical depth of field,
  physically plausible surface response. Exclude cel shading, inked line art, painted illustration
  and 3D rendering.
- **Editorial gouache.** Opaque matte paint shapes, visible dry-brush texture, simplified graphic
  silhouettes, restrained paper grain. Exclude photorealistic rendering, cel shading, 3D rendering,
  glossy airbrushing and vector-flat rendering.
- **Flat graphic vector.** Large flat fields of unmodulated color; no gradients, grain or brush
  texture; confident geometric shapes; a limited palette with one reserved accent color. Exclude
  photorealistic rendering, painterly brush texture, 3D rendering, airbrushed gradients and cel
  shading.

Role phrases that suit concept work, for any bundle:

- **concept art:** polished character and world concept art with clear shape language;
- **illustration:** a finished key illustration with deliberate composition and negative space;
- **environment:** a background painting with clear depth planes and focal staging.

## Compound directions

Neutral compounds that read as recognizable game art. They are starting points, not mandatory
names, and each is stated as visible traits only:

- **explosive aura combat key art:** bold contour, extreme foreshortening, hard cel shadows,
  saturated energy fields, radial debris, and a diagonal attack composition;
- **super-deformed tactical mecha:** modular toy-like machinery, compact proportions, readable team
  colors, orthographic-like staging, and restrained metallic highlights;
- **operator-promotion portrait:** fine tapered line, mature stylized anatomy, a painterly cel
  hybrid, controlled asymmetry, dense costume materials, and atmospheric graphic motifs;
- **luminous creature evolution:** a readable central silhouette, jewel-toned emission, layered
  magical effects, and a clear before-and-after power fantasy without interface chrome;
- **adult sci-fi combat glamour:** clearly adult anatomy, rear or over-the-shoulder action framing,
  fitted technical wardrobe, hard-surface weapon language, crisp cel-painterly rendering, and
  focused emissive accents;
- **adult summer costume cut-in:** clearly adult fashion styling, bright resort light, a confident
  gaze and pose, a polished cel-painterly finish, and an uncluttered promotional composition;
- **high-density pixel combat:** a small native pixel grid scaled up crisply, dark one-pixel
  outlines on actors, a saturated limited palette per area, and dense particles and hit flashes
  that stay readable from a top-down view;
- **cozy 16-bit farm tilemap:** a 16-pixel tile grid, warm greens and soil browns, rounded friendly
  sprites, minimal dithering, and a top-down three-quarter view;
- **loose oil-painted isometric ruin:** an isometric view, thick visible brushwork, warm muted
  stone in low sun, and edges that dissolve into a painterly vignette;
- **minimalist watercolor dream platformer:** a side view, wet-on-wet washes with soft blooms and
  hard dried edges, sparse silhouettes, wide negative space, and a cool palette with one warm
  accent;
- **1930s rubber-hose boss cartoon:** rubber-hose limbs, pie-cut eyes, white gloves, hand-inked
  lines with a slight wobble, watercolor background plates, and, only on request, period film
  grain and faded color;
- **grim inked dungeon tableau:** heavy black ink masses, rough hatching, a desaturated palette with
  one blood-red accent, frieze-like side-on staging, and torchlit chiaroscuro.

## Prompt skeleton

```text
Use case: exploratory game concept cover
Asset type: one finished illustration, landscape

ORIGINAL SCENE AND CONTENT LOCK
- Subjects: exactly <n>: <who>, every person unambiguously adult.
- Wardrobe: <what each wears>.
- Setting: <where and when>.
- Focal action: <one action>.

VISIBLE STYLE AXES
- Medium: <...>
- Character grammar: <...>
- Line: <...>
- Shading: <...>
- Palette and light: <...>
- Surface: <...>
- Depth finish: <...>
- Camera and composition: <...>

HARD CONSTRAINTS
Original artwork only: do not reproduce or imitate any existing game, franchise, studio, artist,
character, emblem or user interface. No words, letters, numbers, pseudo-writing, HUD, captions,
logos, signatures or watermarks anywhere in the image. Every person is unambiguously adult.
Wardrobe and presentation stay tasteful and non-explicit. One coherent image: not a style sampler,
collage, grid or sheet. Keep exactly the subject count and roles stated above.
```

Loosen the presentation line only when the user explicitly asks, for adults only, and within the
provider's policy.

Broad words such as `anime`, `cartoon`, `retro`, `Japanese`, `moe`, `shonen` or `high detail` are
weak alone. Expand them into visible line, shading, palette, surface, proportion, depth and role
choices.
