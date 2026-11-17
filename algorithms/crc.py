from dataclasses import dataclass


@dataclass(frozen=True)
class DivisionStep:
    position: int
    before: str
    operation: str
    after: str


@dataclass(frozen=True)
class CRCEncoding:
    data_bits: str
    generator: str
    padded_data: str
    remainder: str
    transmitted_frame: str
    steps: tuple[DivisionStep, ...]


@dataclass(frozen=True)
class CRCVerification:
    received_frame: str
    generator: str
    remainder: str
    is_valid: bool
    steps: tuple[DivisionStep, ...]


def _normalize_bits(value: str, name: str, minimum_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a binary string.")
    bits = value.strip()
    if len(bits) < minimum_length or any(bit not in "01" for bit in bits):
        raise ValueError(f"{name} must contain at least {minimum_length} binary digit(s).")
    return bits


def _validate_generator(generator: str) -> str:
    bits = _normalize_bits(generator, "Generator polynomial", 2)
    if bits[0] != "1" or bits[-1] != "1":
        raise ValueError("Generator polynomial must start and end with 1.")
    return bits


def _divide(bits: str, generator: str) -> tuple[str, tuple[DivisionStep, ...]]:
    working = list(bits)
    width = len(generator)
    steps = []

    for offset in range(len(working) - width + 1):
        before = "".join(working[offset : offset + width])
        if before[0] == "1":
            for index, divisor_bit in enumerate(generator):
                working[offset + index] = (
                    "0" if working[offset + index] == divisor_bit else "1"
                )
            operation = f"XOR {generator}"
        else:
            operation = "No XOR: leading bit is 0"
        after = "".join(working[offset : offset + width])
        steps.append(
            DivisionStep(
                position=offset + 1,
                before=before,
                operation=operation,
                after=after,
            )
        )

    remainder = "".join(working[-(width - 1) :])
    return remainder, tuple(steps)


def calculate_crc(data_bits: str, generator: str) -> CRCEncoding:
    data = _normalize_bits(data_bits, "Data", 1)
    divisor = _validate_generator(generator)
    padded_data = data + ("0" * (len(divisor) - 1))
    remainder, steps = _divide(padded_data, divisor)
    return CRCEncoding(
        data_bits=data,
        generator=divisor,
        padded_data=padded_data,
        remainder=remainder,
        transmitted_frame=data + remainder,
        steps=steps,
    )


def verify_crc(received_frame: str, generator: str) -> CRCVerification:
    frame = _normalize_bits(received_frame, "Received frame", 1)
    divisor = _validate_generator(generator)
    if len(frame) < len(divisor):
        raise ValueError("Received frame must be at least as long as the generator polynomial.")
    remainder, steps = _divide(frame, divisor)
    return CRCVerification(
        received_frame=frame,
        generator=divisor,
        remainder=remainder,
        is_valid=not any(bit == "1" for bit in remainder),
        steps=steps,
    )


def flip_bit(frame: str, position: int) -> str:
    bits = _normalize_bits(frame, "Frame", 1)
    if not isinstance(position, int) or isinstance(position, bool):
        raise ValueError("Bit position must be a whole number.")
    if not 1 <= position <= len(bits):
        raise ValueError("Bit position must be within the frame.")
    index = position - 1
    flipped = "0" if bits[index] == "1" else "1"
    return bits[:index] + flipped + bits[index + 1 :]
