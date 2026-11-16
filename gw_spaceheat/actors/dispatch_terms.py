"""The dispatch terms a scada and its LTN know by name: the constants a
slow.dispatch.contract's DispatchTerms can name. A market's terms in force
are the MarketMaker's to state (market.terms); until the LTN reads that
word, the one agreement here is the one it offers under."""

from gwsproto.named_types import DispatchTermsFirstIsoneHack

DispatchTerms = DispatchTermsFirstIsoneHack

KNOWN_TERMS: dict[str, DispatchTerms] = {
    DispatchTermsFirstIsoneHack().TypeName: DispatchTermsFirstIsoneHack(),
}


def terms_named(name: str) -> DispatchTerms | None:
    """The terms constant `name` names, or None when the scada does not
    know the agreement."""
    return KNOWN_TERMS.get(name)
