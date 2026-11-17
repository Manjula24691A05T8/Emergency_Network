import streamlit as st

from algorithms.crc import (
    CRCEncoding,
    CRCVerification,
    calculate_crc,
    flip_bit,
    verify_crc,
)


def _show_division_steps(title: str, steps) -> None:
    with st.expander(title):
        lines = ["Position | Window before | Operation | Window after"]
        lines.extend(
            f"{step.position} | {step.before} | {step.operation} | {step.after}"
            for step in steps
        )
        st.code("\n".join(lines), language="text")


def render_error_detection() -> None:
    st.markdown('<div class="eyebrow">DATA LINK / ERROR DETECTION</div>', unsafe_allow_html=True)
    st.title("CRC Error Detection")
    st.markdown(
        "Generate a CRC frame using modulo-2 polynomial division, optionally flip one "
        "transmitted bit, then divide the received frame to check its remainder."
    )

    with st.container(border=True):
        st.markdown('<div class="card-kicker">CRC CONFIGURATION · LOCAL SIMULATION</div>', unsafe_allow_html=True)
        with st.form("crc_error_detection_form"):
            data_bits = st.text_input(
                "Data bits",
                value="1101011011",
                key="crc_data_input",
                help="Enter a binary string of up to 256 bits.",
            )
            generator = st.text_input(
                "Generator polynomial (binary)",
                value="10011",
                key="crc_generator_input",
                help="Use a binary polynomial whose first and last bits are 1.",
            )
            inject_error = st.checkbox(
                "Flip one bit in the transmitted frame",
                key="crc_inject_error_input",
            )
            bit_position = st.number_input(
                "Bit position to flip (1-based)",
                min_value=1,
                max_value=287,
                value=1,
                step=1,
                disabled=not inject_error,
                key="crc_error_position_input",
                help="The position must be within the generated transmitted frame.",
            )
            submitted = st.form_submit_button("Calculate and verify CRC", type="primary")

    if submitted:
        st.session_state.pop("crc_encoding", None)
        st.session_state.pop("crc_verification", None)
        try:
            if len(data_bits.strip()) > 256:
                raise ValueError("Data must contain no more than 256 bits.")
            if len(generator.strip()) > 32:
                raise ValueError("Generator polynomial must contain no more than 32 bits.")
            encoding = calculate_crc(data_bits, generator)
            received_frame = (
                flip_bit(encoding.transmitted_frame, int(bit_position))
                if inject_error
                else encoding.transmitted_frame
            )
            verification = verify_crc(received_frame, encoding.generator)
        except ValueError as error:
            st.error(f"CRC calculation not run: {error}")
        else:
            st.session_state["crc_encoding"] = encoding
            st.session_state["crc_verification"] = verification
            st.session_state["crc_injected_error_position"] = (
                int(bit_position) if inject_error else None
            )

    encoding = st.session_state.get("crc_encoding")
    verification = st.session_state.get("crc_verification")
    if not isinstance(encoding, CRCEncoding) or not isinstance(verification, CRCVerification):
        st.info("Enter binary data and a generator polynomial to calculate and verify a CRC.")
        return

    summary = st.columns(4)
    summary[0].metric("Generator degree", len(encoding.generator) - 1)
    summary[1].metric("CRC remainder", encoding.remainder)
    summary[2].metric("Transmitted frame", encoding.transmitted_frame)
    summary[3].metric("Received remainder", verification.remainder)

    if verification.is_valid:
        st.success("Frame accepted: the received CRC remainder is all zeros.")
    else:
        error_position = st.session_state.get("crc_injected_error_position")
        if error_position is None:
            st.error("Corruption detected: the received CRC remainder is non-zero.")
        else:
            st.error(
                f"Corruption detected at injected bit position {error_position}; "
                "the received CRC remainder is non-zero."
            )

    st.write(f"**Padded data:** `{encoding.padded_data}`")
    st.write(f"**Received frame:** `{verification.received_frame}`")
    _show_division_steps("Encoding division steps", encoding.steps)
    _show_division_steps("Received-frame verification steps", verification.steps)
    st.caption(
        "CRC detects many transmission errors but does not correct them. This is a "
        "binary simulation; no real packets are transmitted."
    )


render_error_detection()
