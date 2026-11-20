# Replacement GALs: verified

The recovered JEDEC files (`gals/uN/uN.jed`, fuse-identical to `gals/uN/uN_named.jed`) were programmed into three
ATF16V8B chips. The copies were checked against the original chips on the bench, then run in the card in place
of the originals. **They behave like the originals in every test, and are drop-in replacements.**

## On the bench

Each copy was programmed with the security fuse off, and the programmer's verify confirmed the fuse map. Each copy
then sat in the same DuPAL V3 ("dupico") board the originals were recorded in, seated the same way (top-aligned in
the ZIF, GND wire from ZIF 10 to ZIF 21, 100 nF across pins 20 and 10). Every move recorded from the original
was replayed on the copy and compared:

| Chip | Mode | Moves replayed | Mismatches | Power-up state |
|---|---|---|---|---|
| U3 | complex (latches) | 79,824 | 0 | 101111, same as the original |
| U4 | registered (+ latches) | 70,880, every clock move included | 0 | 1011101, same as the original |
| U5 | complex (latches, tristate pins 12 and 19) | 12,080 | 0 | 1001110Z, same as the original |

The replay logs are `gals/uN/uN_copy_replay.txt`.

## In the card

Test bench: Amiga 2000, Kickstart 3.1 (and 1.3 for some runs), Workbench 2.05, a GVP A3001 (68030) accelerator,
removed for the 68000 runs. The card ran with the three copies and the originals out. Each combination was compared
with how the same card behaves with its original GALs.

| Boot ROM | CPU | Jumper B | Result (copies and originals alike) |
|---|---|---|---|
| ICD 1.7 (original EPROM) | 68030 | fitted or removed | Cold boot always works. Warm resets alternate between a black screen and a normal boot, and take 20-30 s to start. |
| ICD 1.7 | 68000 | fitted or removed | Boots. Each warm reset first shows a pale yellow screen and 10 power-LED blinks, then boots normally. |
| ICD 1.7 | 68030 | fitted | Copying several MB to RAM: and back, 3 times: no errors, no hangs. |
| ICD 1.7 | 68030 | GAME jumper fitted | No boot from the SCSI drive; the Amiga boots from floppy (the jumper hides the boot ROM). |
| ICD 1.7 | 68030 | jumper A removed | The short cold-boot spin-up wait: too short for the test drive, which then lands on the floppy prompt. Fitted gives the long wait. |
| 4.0 (rebuilt image) | 68000 | fitted or removed | Kickstart 1.3: always boots and warm-resets. Kickstart 3.1: boots only sometimes, but always warm-boots once it has cold-booted. About 100 KiB/s faster than ICD 1.7. |
| 4.0 (rebuilt image) | 68030 | removed | No boot on Kickstart 3.1: dark grey screen (the Kickstart diagnostic screen is still reachable). |
| 4.0 (rebuilt image) | 68030 | fitted | No boot on Kickstart 3.1: Kickstart restarts in a loop; the diagnostic screen is not reachable. |

The quirks in this table (the warm-reset behaviour, the 68030 hangs) belong to the card and its drivers on these
Kickstarts. The original GALs show them too, so they are not faults of the replacements. The 68030 behaviour with
the 4.0 driver is under investigation (see "Known behaviour worth knowing" in `docs/hardware.md`). Now that the
copies are known to be faithful, they can be reprogrammed for experiments while the originals stay untouched.

The boot ROM images are ICD's copyrighted software and are not included here.
