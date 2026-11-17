package com.emergency.network.core;

import java.util.ArrayList;
import java.util.List;

public final class ReliableTransmissionService {
    public record GoBackNRound(
            int roundNumber,
            int baseSequence,
            List<Integer> transmitted,
            List<Integer> received,
            List<Integer> dropped,
            List<Integer> discarded,
            int cumulativeAck,
            boolean retransmission,
            boolean timeout) {
        public GoBackNRound {
            transmitted = List.copyOf(transmitted);
            received = List.copyOf(received);
            dropped = List.copyOf(dropped);
            discarded = List.copyOf(discarded);
        }
    }

    public record GoBackNResult(
            int packetCount, int windowSize, Integer lostPacket, List<GoBackNRound> rounds) {
        public GoBackNResult {
            rounds = List.copyOf(rounds);
        }

        public int retransmissionCount() {
            return rounds.stream()
                    .filter(GoBackNRound::retransmission)
                    .mapToInt(round -> round.transmitted().size())
                    .sum();
        }

        public int timeoutCount() {
            return (int) rounds.stream().filter(GoBackNRound::timeout).count();
        }

        public int totalAcknowledged() {
            return rounds.isEmpty() ? 0 : rounds.get(rounds.size() - 1).cumulativeAck();
        }
    }

    public record SlidingWindowBatch(
            int roundNumber,
            int baseSequence,
            List<Integer> transmitted,
            List<Integer> acknowledged,
            int baseAfterAck) {
        public SlidingWindowBatch {
            transmitted = List.copyOf(transmitted);
            acknowledged = List.copyOf(acknowledged);
        }
    }

    public record SlidingWindowResult(
            int packetCount, int windowSize, List<SlidingWindowBatch> batches) {
        public SlidingWindowResult {
            batches = List.copyOf(batches);
        }

        public int totalAcknowledged() {
            return batches.stream().mapToInt(batch -> batch.acknowledged().size()).sum();
        }
    }

    public GoBackNResult simulateGoBackN(int packetCount, int windowSize) {
        return simulateGoBackN(packetCount, windowSize, null);
    }

    public GoBackNResult simulateGoBackN(int packetCount, int windowSize, Integer lostPacket) {
        validateCounts(packetCount, windowSize);
        if (lostPacket != null && (lostPacket < 1 || lostPacket > packetCount)) {
            throw new IllegalArgumentException(
                    "Lost packet sequence must be between 1 and packet count.");
        }

        List<GoBackNRound> rounds = new ArrayList<>();
        int base = 1;
        int retryEnd = -1;
        boolean retrying = false;
        boolean lossInjected = false;
        while (base <= packetCount) {
            int windowEnd = retrying
                    ? retryEnd
                    : (int) Math.min((long) base + windowSize - 1, packetCount);
            List<Integer> transmitted = sequence(base, windowEnd);
            List<Integer> received = new ArrayList<>();
            List<Integer> dropped = new ArrayList<>();
            List<Integer> discarded = new ArrayList<>();
            int receiverExpected = base;

            for (int sequence : transmitted) {
                if (lostPacket != null && sequence == lostPacket && !lossInjected) {
                    dropped.add(sequence);
                    lossInjected = true;
                } else if (sequence == receiverExpected) {
                    received.add(sequence);
                    receiverExpected++;
                } else {
                    discarded.add(sequence);
                }
            }

            int cumulativeAck = receiverExpected - 1;
            boolean timeout = !dropped.isEmpty();
            rounds.add(new GoBackNRound(
                    rounds.size() + 1,
                    base,
                    transmitted,
                    received,
                    dropped,
                    discarded,
                    cumulativeAck,
                    retrying,
                    timeout));
            if (cumulativeAck >= packetCount) {
                break;
            }
            base = cumulativeAck + 1;
            if (timeout) {
                retryEnd = windowEnd;
                retrying = true;
            } else {
                retryEnd = -1;
                retrying = false;
            }
        }
        return new GoBackNResult(packetCount, windowSize, lostPacket, rounds);
    }

    public SlidingWindowResult simulateSlidingWindow(int packetCount, int windowSize) {
        validateCounts(packetCount, windowSize);
        List<SlidingWindowBatch> batches = new ArrayList<>();
        int base = 1;
        while (base <= packetCount) {
            int end = (int) Math.min((long) base + windowSize - 1, packetCount);
            List<Integer> transmitted = sequence(base, end);
            batches.add(new SlidingWindowBatch(
                    batches.size() + 1, base, transmitted, transmitted,
                    end == Integer.MAX_VALUE ? end : end + 1));
            if (end == packetCount) {
                break;
            }
            base = end + 1;
        }
        return new SlidingWindowResult(packetCount, windowSize, batches);
    }

    private static void validateCounts(int packetCount, int windowSize) {
        if (packetCount < 1) {
            throw new IllegalArgumentException("Packet count must be a positive integer.");
        }
        if (windowSize < 1) {
            throw new IllegalArgumentException("Window size must be a positive integer.");
        }
    }

    private static List<Integer> sequence(int start, int end) {
        List<Integer> values = new ArrayList<>();
        for (long value = start; value <= end; value++) {
            values.add((int) value);
        }
        return values;
    }
}
