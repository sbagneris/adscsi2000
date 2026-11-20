# How the AdSCSI 2000 works

Everything here was established on a real card: continuity measurements (`schematic/continuity/`), the GAL
characterisation (`gals/`), and the boot ROM's behaviour. Signal names match the KiCad schematic and
`schematic/netlist/merged.csv`.

## Parts

| Ref | Part | Role |
|---|---|---|
| U1 | 74F521 | Address comparator: Zorro A16-A23 against the latched base address |
| U2 | 74LS374 | Base address latch (written during Autoconfig) |
| U3 | GAL16V8 (complex mode) | Zorro decode, /SLAVE, Autoconfig state, EPROM and status enables |
| U4 | GAL16V8 (registered mode, clock = CDAC) | 5380 /CS, pseudo-DMA handshake state machine, DMA LED |
| U5 | GAL16V8 (complex mode) | 5380 /IOR and /IOW, data path enables, latch clocks, XRDY wait states |
| U6 | NCR 5380 (socketed) | SCSI bus controller |
| U7 | 74LS245 (A to B only) | Status buffer: J1 jumpers, 5380 DRQ and the handshake bit onto Zorro D8-D15 |
| U8 | 74LS245 (DIR = Zorro READ) | Bus buffer: internal data bus <-> Zorro D8-D15 |
| U9 | 74LS245 (A to B only) | Internal data bus -> Zorro D0-D7 (second byte of 16-bit reads) |
| U10 | 74LS374 | Read latch: internal data bus -> Zorro D8-D15 (first byte of 16-bit reads) |
| U11 | 74LS374 | Write latch: Zorro D0-D7 -> internal data bus (second byte of 16-bit writes) |
| U12 | 27C256 EPROM (socketed) | Boot ROM, even byte lane (D8-D15) |
| RP1 / RP2 | 1 kohm x5 bussed SIP, 2% (CG102G) | Pull-up / pull-down: hold the comparator at $E8 (Autoconfig space) until the base address is latched |
| RP3 | 10 kohm x7 bussed SIP, 2% (8C103G) | Pull-ups: J1 jumper inputs, 5380 /EOP |
| RP4 / RP5 | 220/330 ohm x8 SIP terminators | SCSI termination of 16 signals |
| R1 | 100 ohm 5% | DMA LED |
| R2 / R3 | 1 kohm 5% | /ATN and /RST pull-ups |
| D1 | 1N5395 | VCC -> terminators and TERMPWR (silicon: ~4.1 V; a 1N5817/5818 Schottky gives ~4.6 V) |
| F1 | 1 A fuse | TERMPWR on both SCSI connectors |
| CE1 / CE2 | 47 uF 16 V | Bulk decoupling |
| DC1-DC12 | 0.1 uF | Decoupling (3-hole footprint: 0.1" or 0.4" lead spacing) |

## Autoconfig and address decoding

- Manufacturer 2071, product 1, 64 KB Zorro II board. The Autoconfig nibbles are the first 64 bytes of the EPROM.
- The comparator U1 is enabled by Zorro /CFGIN (`CFGIN`), so the card decodes nothing until its turn in the
  configuration chain. Until configured, U2's outputs are off and RP1/RP2 present A23-A16 = $E8 to the comparator:
  the card answers at $E80000.
- U3: `/SLAVE = /MATCH * /AS * BUSRST` (MATCH = U1's /P=Q). A write to $48 (er_BaseAddress) clocks U2 (`U2CK`),
  which latches the base address from the internal data bus; `U2CK` then holds high until reset ("configured").
  When that bus cycle ends, `U2OE` enables U2 and the card moves to its assigned address.
- EPROM select (U3 `ROMOE`): before configuration the EPROM answers in the lower half (the Autoconfig nibbles);
  after configuration it answers at board offsets $8000 and up, unless the GAME jumper is fitted, which hides the
  boot ROM (the card still configures, but nothing boots from it). The EPROM's /CE is tied to GND.
- ROM byte i is at board offset 2*i (even byte lane); only ROM $4000-$7FFF holds boot code (board $8000+).

## Register map (board offsets, configured)

| Offset | Access | Function |
|---|---|---|
| $00-$1C (stride 4) | read/write | NCR 5380 registers (5380 A0-A2 = Zorro A2-A4); U4 asserts the 5380's /CS here |
| $20 | write | 16-bit data port write (pseudo-DMA) |
| $38 | read | 16-bit data port read (pseudo-DMA) |
| $3C | write | Strobe (written before status reads and transfers; also drives the DMA LED latch) |
| $40 | read | Status byte (U7): bits 0-2 SCSI ID (inverted), bit 3 GAME, bit 4 jumper B, bit 5 jumper A, bit 6 5380 DRQ, bit 7 handshake (U4 `ST7`) |

U3's `SEL` covers offsets $00-$3F (5380 and data port); `STATOE` enables the status buffer U7 for reads at
$40-$7F. The status byte reaches the bus on Zorro D8-D15, so status bit 4 is Zorro D12.

## The 16-bit data port

The 5380 is an 8-bit part on the internal data bus (IDB0-7). The data port moves two bytes per Zorro access:

- Read ($38): U10 (latched earlier byte) drives Zorro D8-D15 and U9 drives the current byte onto Zorro D0-D7,
  both enabled by U5's `RDOE`.
- Write ($20): U8 passes Zorro D8-D15 to the internal bus while U11 latches Zorro D0-D7 for the second byte.
- U4 runs the handshake: a small state machine clocked by CDAC (two internal state registers plus `ST7`) that
  answers the 5380's DRQ with /DACK. U5 generates /IOR, /IOW, the latch clocks (`LATCHCK`, U10 + U11) and XRDY
  wait states (U5 pin 19, an output enabled only when needed: open-collector behaviour on the wired-OR XRDY).
- Interrupts are not used: U5's /INT2 output is never enabled, the 5380's IRQ only feeds U5.

## Jumpers and connectors

| | Pins | Function |
|---|---|---|
| J1 (2x6) | 1-6 = ID0, ID1, ID2, GAME, B, A; 7-12 = GND (pin 6+k opposite pin k) | Fitted jumper = 0. Read through the status byte; GAME also hides the boot ROM (U3). ROM 1.7 uses B for a 64 KB software read cache and A for the cold-boot spin-up wait (8 s or 20 s; removed gives the short wait, which can be too short for a slow drive) |
| J2 (1x3, pin 1 = silkscreen notch) | 1 = CDAC, 2 = U4 clock, 3 = E7M | U4's clock source; 1-2 is bridged by a trace on the board |
| P4 (1x3, pin 1 = notch) | 1 and 3 = LED anode (VCC through R1), 2 = DMALED (U4) | DMA activity LED |
| P5 (1x4) | 1 = +12 V, 2-3 = GND, 4 = +5 V | Drive power |
| P3 (2x25) | standard SCSI-1 50-pin; pin 1 bottom-right (component side, edge connector at the bottom), odd pins GND, 25 open, 26 TERMPWR | Internal SCSI |
| P2 (2x13) | Amiga/Mac DB25 SCSI through a flat IDC cable (header pin 2k-1 -> DB25 k, 2k -> DB25 13+k); 24 = TERMPWR, 26 open | External SCSI |

## Known behaviour worth knowing

- On a 68030 accelerator (GVP A3001 tested) some driver builds hang with jumper B fitted and run reliably with it
  removed. The Kickstart version matters too: on Kickstart 3.1 the 4.0 driver did not boot on the 68030 with
  jumper B fitted or removed (original GALs and replacements alike; see `docs/gal-replacements.md`). Status bit 4 is Zorro D12, which U7 (status), U10 (read latch) and U8 (bus buffer) can all drive; their
  enables (`STATOE`, `RDOE`, `U8OE`) are logically exclusive, so the suspected cause is a short timing overlap on
  fast bus cycles. Under investigation.
