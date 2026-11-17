MAX_TIME_SLOTS = 24


def parse_arrivals(value: str, max_time_slots: int = MAX_TIME_SLOTS) -> list[int]:
    if not isinstance(value, str):
        raise ValueError("Enter comma-separated non-negative whole numbers.")
    if (
        not isinstance(max_time_slots, int)
        or isinstance(max_time_slots, bool)
        or max_time_slots < 1
    ):
        raise ValueError("Maximum time slots must be a positive integer.")

    tokens = [token.strip() for token in value.split(",")]
    if not tokens or any(not token for token in tokens):
        raise ValueError("Enter comma-separated non-negative whole numbers.")
    if len(tokens) > max_time_slots:
        raise ValueError(f"Use no more than {max_time_slots} time slots.")
    try:
        arrivals = [int(token) for token in tokens]
    except ValueError as error:
        raise ValueError("Each time slot must contain a whole number.") from error
    if any(count < 0 for count in arrivals):
        raise ValueError("Arrival counts cannot be negative.")
    return arrivals
