package com.emergency.network.core;

import java.util.ArrayList;
import java.util.List;

public final class LeakyBucketService {
    public static final int MAX_TIME_SLOTS = 24;

    public record Step(
            int tick,
            int arrivals,
            int admitted,
            int queuedBeforeLeak,
            int transmitted,
            int dropped,
            int queuedAfterLeak) {}

    public record Result(int capacity, int outputRate, List<Step> steps) {
        public Result {
            steps = List.copyOf(steps);
            if (steps.isEmpty()) {
                throw new IllegalArgumentException("A result must contain at least one time slot.");
            }
        }

        public long totalArrivals() {
            return steps.stream().mapToLong(Step::arrivals).sum();
        }

        public long totalAdmitted() {
            return steps.stream().mapToLong(Step::admitted).sum();
        }

        public long totalTransmitted() {
            return steps.stream().mapToLong(Step::transmitted).sum();
        }

        public long totalDropped() {
            return steps.stream().mapToLong(Step::dropped).sum();
        }

        public int peakOccupancy() {
            return steps.stream().mapToInt(Step::queuedBeforeLeak).max().orElse(0);
        }

        public int congestedSlots() {
            return (int) steps.stream()
                    .filter(step -> step.dropped() > 0 || step.queuedBeforeLeak() == capacity)
                    .count();
        }

        public double congestionRatePercent() {
            return 100.0 * congestedSlots() / steps.size();
        }

        public String congestionStatus() {
            if (totalDropped() > 0) {
                return "Congested";
            }
            return peakOccupancy() == capacity ? "At capacity" : "Stable";
        }
    }

    public record ProfileComparison(Result normal, Result stress) {}

    public Result simulate(List<Integer> arrivals, int capacity, int outputRate) {
        validatePositive(capacity, "Bucket capacity");
        validatePositive(outputRate, "Output rate");
        if (arrivals == null || arrivals.isEmpty()) {
            throw new IllegalArgumentException("Provide at least one time slot of incoming traffic.");
        }
        int queued = 0;
        List<Step> steps = new ArrayList<>(arrivals.size());
        for (int index = 0; index < arrivals.size(); index++) {
            Integer incoming = arrivals.get(index);
            if (incoming == null || incoming < 0) {
                throw new IllegalArgumentException("Arrivals must be non-negative integers.");
            }
            int admitted = Math.min(incoming, capacity - queued);
            int dropped = incoming - admitted;
            queued += admitted;
            int beforeLeak = queued;
            int transmitted = Math.min(outputRate, queued);
            queued -= transmitted;
            steps.add(new Step(
                    index + 1, incoming, admitted, beforeLeak, transmitted, dropped, queued));
        }
        return new Result(capacity, outputRate, steps);
    }

    public ProfileComparison compareProfiles(
            List<Integer> arrivals, int capacity, int normalOutputRate, int stressOutputRate) {
        Result normal = simulate(arrivals, capacity, normalOutputRate);
        Result stress = simulate(arrivals, capacity, stressOutputRate);
        if (stressOutputRate >= normalOutputRate) {
            throw new IllegalArgumentException(
                    "The congestion-stress output rate must be lower than the normal rate.");
        }
        return new ProfileComparison(normal, stress);
    }

    public List<Integer> parseArrivals(String value) {
        return parseArrivals(value, MAX_TIME_SLOTS);
    }

    public List<Integer> parseArrivals(String value, int maxTimeSlots) {
        if (value == null) {
            throw new IllegalArgumentException("Enter comma-separated non-negative whole numbers.");
        }
        validatePositive(maxTimeSlots, "Maximum time slots");
        String[] tokens = value.split(",", -1);
        if (tokens.length > maxTimeSlots) {
            throw new IllegalArgumentException("Use no more than " + maxTimeSlots + " time slots.");
        }
        List<Integer> arrivals = new ArrayList<>(tokens.length);
        for (String token : tokens) {
            String trimmed = token.trim();
            if (trimmed.isEmpty()) {
                throw new IllegalArgumentException(
                        "Enter comma-separated non-negative whole numbers.");
            }
            try {
                int count = Integer.parseInt(trimmed);
                if (count < 0) {
                    throw new IllegalArgumentException("Arrival counts cannot be negative.");
                }
                arrivals.add(count);
            } catch (NumberFormatException exception) {
                throw new IllegalArgumentException("Each time slot must contain a whole number.", exception);
            }
        }
        return List.copyOf(arrivals);
    }

    private static void validatePositive(int value, String name) {
        if (value < 1) {
            throw new IllegalArgumentException(name + " must be a positive integer.");
        }
    }
}
