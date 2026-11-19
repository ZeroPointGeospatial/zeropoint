# Printing the plates

Notes for whoever sends the files to a print shop. `export_print.py` writes
the files described here.

## Which file

Every A2 plate comes as two files.

| File | Size | Use it when |
| --- | --- | --- |
| `<plate>_A2.jpg` | 420 × 594 mm, 4961 × 7016 px | The shop prints on a roll and cuts to the edge of the image. This is how most A2 to A0 inkjet prints are made, so it is the file to send by default. |
| `<plate>_A2_bleed.jpg` | 426 × 600 mm, 5031 × 7086 px | The shop asks for bleed, or cuts a stack on a guillotine. The extra 3 mm on each side is cut off, so a cut that lands slightly out never shows a white edge. |

Do not let the bleed file be printed "fit to A2": the picture comes out 1.4 %
small with the bleed inside the sheet. Say "print at 100 %, trim to
420 × 594 mm".

The city prints (`mombasa-gold.jpg` and the others) are one file each, with
no bleed. They match the Nairobi prints: 6744 × 8540 px, a proportion of
1 : 1.266, slightly taller than 4 : 5.

## Size

| Print | Scale the A2 file to | Resolution on paper |
| --- | --- | --- |
| A2, 420 × 594 mm | 100 % | 300 ppi |
| A1, 594 × 841 mm | 141.4 % | 212 ppi |
| A0, 841 × 1189 mm | 200 % | 150 ppi |

150 ppi is enough for A0 at the distance a wall map is read from. If a
customer wants a sharper A0 of a line plate (rivers, roads, counties,
contours), render it again with `DPI=600 sh render_all.sh`. The relief and
population plates gain little, because the elevation data is no finer.

City prints at their native size are about 560 × 708 mm. At 40 cm wide
they are 50.7 cm tall, at 50 cm wide 63.3 cm, at 60 cm wide 76 cm. They do
not fill an A-size frame; use a frame made to the print, or a mount.

## Colour

- The files are sRGB with the profile embedded. Ask the shop to print with
  colour management on and to leave the conversion to their printer profile.
  Do not convert the files to CMYK yourself.
- Ask for pigment inkjet (giclée) on a matte or satin paper of 200 gsm or
  more. Avoid gloss: the dark plates turn into mirrors behind glass.
- The dark plates (rivers, roads, contours and the city prints) are almost
  solid ink. Two things to check on the first print of each: that the dark
  green or near-black does not come out blotchy or bronzed, and that the
  finest lines (0.075 mm on the rivers plate) have not filled in. If the
  thin lines vanish on matte paper, try satin.
- Before a first order, pay for a strip test: a 10 cm wide strip from the
  middle of the plate at full size, on the paper you intend to sell. It
  costs little and shows colour, black and line weight at once. Keep the
  approved strip and ask for later prints to match it.

Colours on a phone or laptop are brighter than paper can be. Judge the
prints, not the screen.

## Framing

On the A2 plates all type and the title block sit at least 22 mm inside the
cut edge, so a frame rebate of 5 to 10 mm hides nothing. The light plates
are drawn on a paper-coloured ground (`#f1f0eb`), not white: if the print is
mounted, a white or off-white mount works, a cream one fights it.

The city prints are tighter. The coordinates and the credit line sit about
7 mm above the bottom edge at full size, as they do on the Nairobi
originals. Frame them with a rebate of 5 mm or less, or float-mount them,
and check the first one before the back is sealed.

## Credits

Every plate carries its data credit in the bottom line. The licences
(Copernicus, OpenStreetMap, Kontur, Hansen) allow selling the prints on the
condition that the credit stays, so do not crop it off. The two Nairobi
gold prints made before this pipeline do not carry an OpenStreetMap credit;
add "© OpenStreetMap contributors" to them before the next print run.
