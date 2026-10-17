# Rejected eager report layout: repeated broadcast names

This is an authored analytical negative, not an executed profile/native test.
It preserves the allocation failure discovered before production implementation.

Consider16 row dimensions, each with one empty-string label, one scalar float64
measurement and32 direct columns c0..c31 repeating all16 dimensions. Give each
dimension a128-byte ASCII name consisting of127 ampersands followed by one
unique ASCII letter. All names are opaque legal names. The row grain is one;
there are no support records. Original logical names/dtypes must remain exact.

The rejected report layout printed the complete logical broadcast name list
separately for every column. Each name alone expands to127*5+1=636 HTML text
bytes, so the repeated broadcast names alone emit32*16*636=325632 bytes.
No punctuation, other summaries, headers, values or static report text is in
that subtotal.

Under unchanged conservative projections (three-reason tuple J268/P1452):

- row_dims J12337/P12800
- units J773/P13144
- row keys J12385/P14848
- row values J1669/P13144
- row reasons J9221/P55512
- one row J23390/P84852; rows container J23392/P85492
- result B36744 including LF; result M114128 including136 private/pointer bytes
- the one-report half of the released-result envelope M+3B is224360 bytes

Thus325632>224360 before the rest of the report. Two eager buffers cannot be
claimed to fit2M+6B for that layout. Occupied plan Z or descriptor Dmeta cannot
be borrowed. A full compiler run still has to establish the concrete family's
complete admission; the above is an exact shape/allocation counterexample,
not a claim that every jointly maximal profile fits512MiB.

The proposed correction keeps one full logical row_dims dictionary and prints
explicit key:NN references in every column broadcast list. Six-character
references cost at most16*(8+1)+1=145 canonical JSON bytes per column, while the
full original logical names stay present in the dictionary and exact typed
headers/schema. The convenience-buffer dominance and streaming-writer route
remain explicit separate review obligations in BUNDLE-FORMAT-INTERFACE.md.
