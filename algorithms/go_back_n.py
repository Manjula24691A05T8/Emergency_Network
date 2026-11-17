from dataclasses import dataclass


@dataclass(frozen=True)
class GoBackNRound:
    round_number: int
    base_sequence: int
    transmitted: tuple[int, ...]
    received: tuple[int, ...]
    dropped: tuple[int, ...]
    discarded: tuple[int, ...]
    cumulative_ack: int
    retransmission: bool
    timeout: bool


@dataclass(frozen=True)
class GoBackNResult:
    packet_count: int
    window_size: int
    lost_packet: int | None
    rounds: tuple[GoBackNRound, ...]

    @property
    def retransmission_count(self) -> int:
        return sum(
            len(round_result.transmitted)
            for round_result in self.rounds
            if round_result.retransmission
        )

    @property
    def timeout_count(self) -> int:
        return sum(round_result.timeout for round_result in self.rounds)

    @property
    def total_acknowledged(self) -> int:
        return self.rounds[-1].cumulative_ack if self.rounds else 0


def simulate_go_back_n(
    packet_count: int,
    window_size: int,
    lost_packet: int | None = None,
) -> GoBackNResult:
    if not isinstance(packet_count, int) or isinstance(packet_count, bool) or packet_count < 1:
        raise ValueError("Packet count must be a positive integer.")
    if not isinstance(window_size, int) or isinstance(window_size, bool) or window_size < 1:
        raise ValueError("Window size must be a positive integer.")
    if lost_packet is not None and (
        not isinstance(lost_packet, int)
        or isinstance(lost_packet, bool)
        or not 1 <= lost_packet <= packet_count
    ):
        raise ValueError("Lost packet sequence must be between 1 and packet count.")

    rounds = []
    base = 1
    retry_end = None
    retrying = False
    loss_injected = False

    while base <= packet_count:
        window_end = (
            retry_end
            if retrying and retry_end is not None
            else min(base + window_size - 1, packet_count)
        )
        transmitted = tuple(range(base, window_end + 1))
        received = []
        dropped = []
        discarded = []
        receiver_expected = base

        for sequence in transmitted:
            if sequence == lost_packet and not loss_injected:
                dropped.append(sequence)
                loss_injected = True
            elif sequence == receiver_expected:
                received.append(sequence)
                receiver_expected += 1
            else:
                discarded.append(sequence)

        cumulative_ack = receiver_expected - 1
        timeout = bool(dropped)
        rounds.append(
            GoBackNRound(
                round_number=len(rounds) + 1,
                base_sequence=base,
                transmitted=transmitted,
                received=tuple(received),
                dropped=tuple(dropped),
                discarded=tuple(discarded),
                cumulative_ack=cumulative_ack,
                retransmission=retrying,
                timeout=timeout,
            )
        )

        base = cumulative_ack + 1
        if timeout:
            retry_end = window_end
            retrying = True
        else:
            retry_end = None
            retrying = False

    return GoBackNResult(
        packet_count=packet_count,
        window_size=window_size,
        lost_packet=lost_packet,
        rounds=tuple(rounds),
    )
