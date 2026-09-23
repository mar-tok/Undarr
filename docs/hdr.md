# HDR

Undarr reads the HDR type of every scanned file (HDR10, HDR10+, HLG, Dolby Vision) and shows it in the storage view, the queue, and as a skip rule field.

Undarr keeps the HDR10 static metadata when it transcodes an HDR10 file, so the file that replaces the original is an HDR10 file too. Undarr removes the HDR10+ dynamic metadata when it transcodes an HDR10+ file, so it replaces an HDR10+ file with an HDR10 file. To keep HDR10+ files as they are, add the skip rule `hdr_type equals hdr10+` to the library.

> [!CAUTION]
> Undarr removes the Dolby Vision metadata when it transcodes a Dolby Vision file, and only the base layer is left. Undarr replaces a profile 8.1 file with an HDR10 file, because profile 8.1 has an HDR10 base layer. Undarr replaces a profile 5 file with a file that shows wrong colors, because only a Dolby Vision player can display the profile 5 base layer. To keep Dolby Vision files as they are, add the skip rule `hdr_type equals dolby_vision` to the library.
