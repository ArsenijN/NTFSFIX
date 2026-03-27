# NTFSFIX
Process bad blocks from Victoria easier to use with jamersonpro/ntfsmarkbad program

# NtfsMarkBad quirks
It does not support NTFS with cluster size >64 KB, so use only the 64 KB as highest

# How To Use
The input bads list is next structure from Victoria (can be used directly):
```
1298993985, 2048  ;665 GB  Scan bad
1298998081, 2048  ;665 GB  Timeout
```
