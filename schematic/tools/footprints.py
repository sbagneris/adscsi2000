"""Reference -> footprint (library adscsi, schematic/kicad/adscsi.pretty, built by pcb_lib.py). No pcbnew
import here: the schematic generator uses it to fill the Footprint fields."""
FOOTPRINT = {
    **{u: 'DIP-20_W7.62mm' for u in ('U1', 'U2', 'U7', 'U8', 'U9', 'U10', 'U11')},
    **{u: 'DIP-20_W7.62mm_Socket' for u in ('U3', 'U4', 'U5')},
    'U6': 'DIP-40_W15.24mm_Socket', 'U12': 'DIP-28_W15.24mm_Socket',
    'RP1': 'SIP-6_P2.54mm', 'RP2': 'SIP-6_P2.54mm', 'RP3': 'SIP-8_P2.54mm', 'RP4': 'SIP-10_P2.54mm', 'RP5': 'SIP-10_P2.54mm',
    'P3': 'IDC-Box_2x25_P2.54mm', 'P2': 'IDC-Box_2x13_P2.54mm', 'J1': 'PinHeader_2x06_P2.54mm_ColNumbered',
    'J2': 'PinHeader_1x03_P2.54mm', 'P4': 'PinHeader_1x03_P2.54mm', 'P5': 'DrivePower_1x04_P2.54mm',
    'R1': 'Axial_P10.16mm', 'R2': 'Axial_P10.16mm', 'R3': 'Axial_P10.16mm',
    'D1': 'Diode_Axial_P10.16mm', 'F1': 'Axial_P10.16mm_D1.0',
    'CE1': 'CP_Radial_P2.54_D5.0', 'CE2': 'CP_Radial_P2.54_D5.0',
    **{f'DC{n}': 'C_Disc_3pad_P2.54_P10.16' for n in range(1, 13)},
    'P1': 'Zorro2_Edge_100',
}

