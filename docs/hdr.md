# HDR

Undarr reads the HDR type of every scanned file (HDR10, HDR10+, HLG, Dolby Vision) and shows it in the storage view, the queue, and as a skip rule field.

HDR10 static metadata is kept through a transcode, and the output is detected as HDR10 again. A transcode drops HDR10+ dynamic metadata. The output is an HDR10 file. To keep HDR10+ files as they are, add the skip rule `hdr_type equals hdr10+` to the library.

> [!CAUTION]
> A transcode keeps the base layer and drops the Dolby Vision metadata. Profile 8.1 files have an HDR10 base layer. Their output is an HDR10 file. Profile 5 files have a base layer that only Dolby Vision players can display. Their output is expected to have wrong colors. Profile 5 has not been tested yet. To keep Dolby Vision files as they are, add the skip rule `hdr_type equals dolby_vision` to the library.
