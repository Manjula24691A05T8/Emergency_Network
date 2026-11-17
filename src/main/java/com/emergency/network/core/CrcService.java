package com.emergency.network.core;

import java.util.ArrayList;
import java.util.List;

public final class CrcService {
    public record DivisionStep(int position, String before, String operation, String after) {}

    public record Encoding(
            String dataBits,
            String generator,
            String paddedData,
            String remainder,
            String transmittedFrame,
            List<DivisionStep> steps) {
        public Encoding {
            steps = List.copyOf(steps);
        }
    }

    public record Verification(
            String receivedFrame,
            String generator,
            String remainder,
            boolean valid,
            List<DivisionStep> steps) {
        public Verification {
            steps = List.copyOf(steps);
        }
    }

    public Encoding calculate(String dataBits, String generator) {
        String data = normalizeBits(dataBits, "Data", 1);
        String divisor = validateGenerator(generator);
        String padded = data + "0".repeat(divisor.length() - 1);
        Division division = divide(padded, divisor);
        return new Encoding(
                data,
                divisor,
                padded,
                division.remainder(),
                data + division.remainder(),
                division.steps());
    }

    public Verification verify(String receivedFrame, String generator) {
        String frame = normalizeBits(receivedFrame, "Received frame", 1);
        String divisor = validateGenerator(generator);
        if (frame.length() < divisor.length()) {
            throw new IllegalArgumentException(
                    "Received frame must be at least as long as the generator polynomial.");
        }
        Division division = divide(frame, divisor);
        return new Verification(
                frame,
                divisor,
                division.remainder(),
                division.remainder().chars().noneMatch(bit -> bit == '1'),
                division.steps());
    }

    public String flipBit(String frame, int position) {
        String bits = normalizeBits(frame, "Frame", 1);
        if (position < 1 || position > bits.length()) {
            throw new IllegalArgumentException("Bit position must be within the frame.");
        }
        int index = position - 1;
        char flipped = bits.charAt(index) == '1' ? '0' : '1';
        return bits.substring(0, index) + flipped + bits.substring(index + 1);
    }

    private static String normalizeBits(String value, String name, int minimumLength) {
        if (value == null) {
            throw new IllegalArgumentException(name + " must be a binary string.");
        }
        String bits = value.trim();
        if (bits.length() < minimumLength
                || bits.chars().anyMatch(bit -> bit != '0' && bit != '1')) {
            throw new IllegalArgumentException(
                    name + " must contain at least " + minimumLength + " binary digit(s).");
        }
        return bits;
    }

    private static String validateGenerator(String generator) {
        String bits = normalizeBits(generator, "Generator polynomial", 2);
        if (bits.charAt(0) != '1' || bits.charAt(bits.length() - 1) != '1') {
            throw new IllegalArgumentException("Generator polynomial must start and end with 1.");
        }
        return bits;
    }

    private static Division divide(String bits, String generator) {
        char[] working = bits.toCharArray();
        int width = generator.length();
        List<DivisionStep> steps = new ArrayList<>();
        for (int offset = 0; offset <= working.length - width; offset++) {
            String before = new String(working, offset, width);
            String operation;
            if (working[offset] == '1') {
                for (int index = 0; index < width; index++) {
                    working[offset + index] =
                            working[offset + index] == generator.charAt(index) ? '0' : '1';
                }
                operation = "XOR " + generator;
            } else {
                operation = "No XOR: leading bit is 0";
            }
            steps.add(new DivisionStep(
                    offset + 1,
                    before,
                    operation,
                    new String(working, offset, width)));
        }
        return new Division(
                new String(working, working.length - width + 1, width - 1),
                List.copyOf(steps));
    }

    private record Division(String remainder, List<DivisionStep> steps) {}
}
