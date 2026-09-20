# assets/

The FaMAF CVA6 Project's mark, and the palette the project's pages and marks share.

| File                                             | What it is                                                                                           |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| [FaMAF_CVA6_header.svg](FaMAF_CVA6_header.svg)   | The lockup at the top of the root `README.md`: the mark, the name and the line under it, 1280 by 260 |
| [FaMAF_CVA6_logo.svg](FaMAF_CVA6_logo.svg)       | The mark alone on the 64 grid, drawn at 128 px, for a page heading or a slide                        |
| [FaMAF_CVA6_favicon.svg](FaMAF_CVA6_favicon.svg) | The same mark on the 16 grid, with the detail an icon that small can carry                           |

## The mark

A trace row above a waveform row, each feeding four stage cells, and the cells of the two rows at the same four cycles. That is the project in one picture: a gem5 MinorCPU read from a debug trace and the CVA6 RTL read from a VCD, lined up cycle for cycle. The accent bar on the left is the calibration that ties them.

It belongs to the same family as the viewers' marks, which are in each viewer's `docs/` folder. [MinorFlow](../viewers/MinorFlow/docs/MinorFlow_logo.svg) and [CVA6Flow](../viewers/CVA6Flow/docs/CVA6Flow_logo.svg) each show one machine, their rows staircasing one cycle later down the tile, and [FlowCompare](../viewers/FlowCompare.html) pairs the two with an amber marker where they drift. The project's mark drops the staircase and aligns the rows instead, since what this repository is for is the alignment.

## The palette

The viewers' `css-tokens` block, which the three pages share and these marks are drawn from.

| Token      | Value                      | Used for                                  |
| ---------- | -------------------------- | ----------------------------------------- |
| `--bg`     | `#18181a`                  | The page and the tile                     |
| `--text`   | `#e4e2dc`                  | Body text and the wordmark                |
| `--text2`  | `#a0a09a`                  | Secondary text, the line under the name   |
| `--accent` | `#3ecf9a`                  | The accent bar, links, the active control |
| hairline   | `rgba(255, 255, 255, .12)` | The tile's edge                           |

The stage cells carry the colours the viewers give the stages they draw, lifted a little so they hold up at icon size: `#6cbbe4` fetch, `#2f7fb5` decode's input, `#7b4fc4` decode and `#2a9a66` execute. The grey of a trace line is `#62625d` with a `#7a8aa6` head, and a waveform is `#7a8aa6` throughout.

## Redrawing them

`temp/logo/make_logos.py` draws every mark in the project, the viewers' and this one, from one set of numbers. It needs `fontTools` for the wordmark outlines and the IBM Plex Mono files in `temp/logo/fonts/`.

```bash
python3 temp/logo/make_logos.py            # rewrite the marks in assets/ and in both viewers' docs/
python3 temp/logo/make_logos.py --patch    # and put them into the three pages
```

`temp/` is working notes and is not tracked, so the generator is not part of a clone. The files in this folder are, and they are what a reader sees.
