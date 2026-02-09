"""AX.25 frame handling for RFMP."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AX25Address:
    """AX.25 address (callsign with SSID)."""
    callsign: str
    ssid: int = 0

    def __post_init__(self):
        """Validate address."""
        # Uppercase callsign
        self.callsign = self.callsign.upper()

        # Validate callsign length (max 6 characters)
        if len(self.callsign) > 6:
            raise ValueError(f"Callsign too long: {self.callsign}")

        # Validate SSID range
        if not 0 <= self.ssid <= 15:
            raise ValueError(f"SSID must be 0-15, got {self.ssid}")

    def encode(self, is_last: bool = False) -> bytes:
        """
        Encode address to AX.25 format.

        Args:
            is_last: True if this is the last address in the list

        Returns:
            7-byte encoded address
        """
        # Pad callsign to 6 characters
        padded = self.callsign.ljust(6, ' ')

        # Shift left by 1 bit
        result = bytearray()
        for char in padded:
            result.append(ord(char) << 1)

        # Add SSID byte
        ssid_byte = 0b01100000  # Reserved bits
        ssid_byte |= (self.ssid << 1)

        if is_last:
            ssid_byte |= 0x01  # Set address extension bit

        result.append(ssid_byte)

        return bytes(result)

    @classmethod
    def decode(cls, data: bytes) -> Optional['AX25Address']:
        """
        Decode AX.25 address from bytes.

        Args:
            data: 7-byte encoded address

        Returns:
            Decoded address or None if invalid
        """
        if len(data) != 7:
            return None

        # Decode callsign (first 6 bytes)
        callsign_chars = []
        for i in range(6):
            char = chr(data[i] >> 1)
            if char != ' ':
                callsign_chars.append(char)

        callsign = ''.join(callsign_chars)

        # Decode SSID (7th byte)
        ssid_byte = data[6]
        ssid = (ssid_byte >> 1) & 0x0F

        return cls(callsign=callsign, ssid=ssid)

    def __str__(self) -> str:
        """String representation."""
        if self.ssid == 0:
            return self.callsign
        return f"{self.callsign}-{self.ssid}"

    @classmethod
    def parse(cls, address_str: str) -> 'AX25Address':
        """
        Parse address from string format.

        Args:
            address_str: Address string (e.g., "N0CALL" or "N0CALL-1")

        Returns:
            Parsed address
        """
        if '-' in address_str:
            callsign, ssid_str = address_str.split('-', 1)
            ssid = int(ssid_str)
        else:
            callsign = address_str
            ssid = 0

        return cls(callsign=callsign, ssid=ssid)


@dataclass
class AX25Frame:
    """AX.25 UI frame for RFMP."""
    destination: AX25Address
    source: AX25Address
    digipeaters: List[AX25Address]
    control: int  # Control field (0x03 for UI)
    pid: int  # Protocol ID (0xF0 for no L3)
    info: bytes  # Information field (RFMP data)

    def encode(self) -> bytes:
        """
        Encode frame to AX.25 format.

        Returns:
            Encoded frame bytes
        """
        result = bytearray()

        # Add destination address
        result.extend(self.destination.encode(is_last=False))

        # Add source address
        is_last = len(self.digipeaters) == 0
        result.extend(self.source.encode(is_last=is_last))

        # Add digipeater addresses if any
        for i, digi in enumerate(self.digipeaters):
            is_last = (i == len(self.digipeaters) - 1)
            result.extend(digi.encode(is_last=is_last))

        # Add control field
        result.append(self.control)

        # Add PID field
        result.append(self.pid)

        # Add information field
        result.extend(self.info)

        return bytes(result)

    @classmethod
    def decode(cls, data: bytes) -> Optional['AX25Frame']:
        """
        Decode AX.25 frame from bytes.

        Args:
            data: Raw frame bytes

        Returns:
            Decoded frame or None if invalid
        """
        if len(data) < 16:  # Minimum frame size
            return None

        try:
            # Decode destination address
            destination = AX25Address.decode(data[0:7])
            if not destination:
                return None

            # Decode source address
            source = AX25Address.decode(data[7:14])
            if not source:
                return None

            # Check for digipeaters
            digipeaters = []
            idx = 14

            # Check if source has address extension bit set
            if not (data[13] & 0x01):
                # There are digipeaters
                while idx + 7 <= len(data):
                    digi = AX25Address.decode(data[idx:idx + 7])
                    if not digi:
                        break
                    digipeaters.append(digi)
                    idx += 7

                    # Check for address extension bit
                    if data[idx - 1] & 0x01:
                        break

            # Get control field
            if idx >= len(data):
                return None
            control = data[idx]
            idx += 1

            # Get PID field
            if idx >= len(data):
                return None
            pid = data[idx]
            idx += 1

            # Get information field
            info = data[idx:]

            return cls(
                destination=destination,
                source=source,
                digipeaters=digipeaters,
                control=control,
                pid=pid,
                info=info
            )

        except Exception:
            return None

    @classmethod
    def create_ui_frame(cls,
                        source: str,
                        destination: str = "RFMP",
                        info: bytes = b'',
                        digipeaters: Optional[List[str]] = None) -> 'AX25Frame':
        """
        Create a UI frame for RFMP.

        Args:
            source: Source callsign
            destination: Destination callsign (default "RFMP")
            info: Information field data
            digipeaters: Optional list of digipeater callsigns

        Returns:
            New AX.25 UI frame
        """
        src_addr = AX25Address.parse(source)
        dst_addr = AX25Address.parse(destination)

        digi_addrs = []
        if digipeaters:
            for digi in digipeaters:
                digi_addrs.append(AX25Address.parse(digi))

        return cls(
            destination=dst_addr,
            source=src_addr,
            digipeaters=digi_addrs,
            control=0x03,  # UI frame
            pid=0xF0,  # No L3 protocol
            info=info
        )