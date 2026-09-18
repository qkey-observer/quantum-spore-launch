"""Bitstring → full launch spec. The map is hashed before the run.

A salt still comes from keccak256(utf8(bitstring)). The map decides whether
that shot launches, the name/symbol, tax, and delay. Skipped shots stay in
the public rounds journal so "47 measured, 12 launched" is checkable.
"""

from __future__ import annotations

from typing import Any

from .derive import BITSTRING_PATTERN, keccak256, plan_hash
from .errors import QuantumLaunchError


class MapError(QuantumLaunchError):
    """Launch map is invalid or does not match the measured bitstring."""


def load_map(value: dict[str, Any]) -> dict[str, Any]:
    want = dict(value)
    want.pop("comment", None)
    version = want.get("schemaVersion")
    if version == 2:
        return _load_direct(want)
    if version != 1:
        raise MapError("launch map schemaVersion must be 1 or 2")
    width = want.get("width")
    if not isinstance(width, int) or not 2 <= width <= 64:
        raise MapError("launch map width must be 2..64")
    if want.get("msbFirst") is not True:
        raise MapError("launch map must declare msbFirst true (bitstring convention)")
    launch_bit = want.get("launchBit")
    if not isinstance(launch_bit, int) or not 0 <= launch_bit < width:
        raise MapError("launchBit is out of range")
    if want.get("launchWhen") not in {"0", "1"}:
        raise MapError("launchWhen must be the character 0 or 1")
    _check_bits(want.get("taxBits"), width, "taxBits")
    _check_bits(want.get("delayBits"), width, "delayBits")
    _check_bits(want.get("nameBits"), width, "nameBits")
    tax_tiers = want.get("taxTiersBps")
    delay_tiers = want.get("delayTiersSeconds")
    names = want.get("names")
    if not isinstance(tax_tiers, list) or not tax_tiers:
        raise MapError("taxTiersBps missing")
    if not isinstance(delay_tiers, list) or not delay_tiers:
        raise MapError("delayTiersSeconds missing")
    if not isinstance(names, dict) or not names:
        raise MapError("names table missing")
    if 1 << len(want["taxBits"]) != len(tax_tiers):
        raise MapError("taxTiersBps length must be 2^len(taxBits)")
    if 1 << len(want["delayBits"]) != len(delay_tiers):
        raise MapError("delayTiersSeconds length must be 2^len(delayBits)")
    if 1 << len(want["nameBits"]) != len(names):
        raise MapError("names table size must be 2^len(nameBits)")
    for key, row in names.items():
        if not isinstance(key, str) or not BITSTRING_PATTERN.fullmatch(key) or len(key) != len(want["nameBits"]):
            raise MapError(f"names key is not a bitstring of length {len(want['nameBits'])}: {key}")
        if not isinstance(row, dict) or not row.get("name") or not row.get("symbol"):
            raise MapError(f"names[{key}] needs name and symbol")
    want["mode"] = "table"
    return want


def _load_direct(want: dict[str, Any]) -> dict[str, Any]:
    """schemaVersion 2: fields are sliced from the measured bits.

    Name/symbol are spelled from a published 32-character alphabet — the QPU
    does not pick from a QKEY table. Quote, logo, config id and opening buy
    are indices into published menus (real addresses/URLs, hashed with the map).
    """
    if want.get("mode") != "direct":
        raise MapError("schemaVersion 2 must set mode to direct")
    width = want.get("width")
    if not isinstance(width, int) or not 2 <= width <= 64:
        raise MapError("launch map width must be 2..64")
    if want.get("msbFirst") is not True:
        raise MapError("launch map must declare msbFirst true (bitstring convention)")
    shots_per = want.get("shotsPerSpec", 1)
    if shots_per not in (1, 2, 4):
        raise MapError("shotsPerSpec must be 1, 2 or 4")
    want["shotsPerSpec"] = shots_per
    want["specWidth"] = width * shots_per
    fields = want.get("fields")
    if not isinstance(fields, dict):
        raise MapError("direct map needs fields")
    has_suffix = "suffix" in fields
    has_chars = "name" in fields and "symbol" in fields
    if has_suffix:
        required = ("launch", "creatorTaxBps", "delaySeconds", "buyback", "feeDestination", "suffix")
    elif has_chars:
        required = ("launch", "creatorTaxBps", "delaySeconds", "buyback", "feeDestination", "name", "symbol")
        alphabet = want.get("alphabet")
        if not isinstance(alphabet, str) or len(alphabet) != 32 or len(set(alphabet)) != 32:
            raise MapError("direct char encoding needs a 32-character unique alphabet")
        if len(fields["name"]["bits"]) % 5 or len(fields["symbol"]["bits"]) % 5:
            raise MapError("name/symbol bit lengths must be multiples of 5")
    else:
        raise MapError("direct map needs fields.suffix or fields.name+fields.symbol")
    for name in required:
        spec = fields.get(name)
        if not isinstance(spec, dict) or not isinstance(spec.get("bits"), list):
            raise MapError(f"fields.{name}.bits missing")
        _check_bits(spec["bits"], want["specWidth"], f"fields.{name}.bits")
    for optional in (
        "quote", "logo", "launchConfigId", "openingBuy", "extraName",
        "feeRecipient", "exemptions", "nextLayers", "nextShots", "nextBackend",
        "website", "x", "telegram",
    ):
        if optional in fields:
            _check_bits(fields[optional]["bits"], want["specWidth"], f"fields.{optional}.bits")
    if fields["launch"].get("when") not in {"0", "1"}:
        raise MapError("fields.launch.when must be 0 or 1")
    circuit = want.get("circuit")
    if not isinstance(circuit, dict) or circuit.get("kind") != "hardware_efficient":
        raise MapError("direct map must pin a hardware_efficient circuit")
    if circuit.get("qubits") != width:
        raise MapError("circuit.qubits must equal map width")
    layers = circuit.get("layers")
    if not isinstance(layers, int) or not 1 <= layers <= 64:
        raise MapError("circuit.layers must be 1..64")
    if not isinstance(circuit.get("angleSeed"), str) or not circuit["angleSeed"]:
        raise MapError("circuit.angleSeed is part of the public rule and must be set")
    menus = want.get("menus") or {}
    if not isinstance(menus, dict):
        raise MapError("menus must be an object")
    if "quote" in fields:
        quotes = menus.get("quotes")
        if not isinstance(quotes, list) or not quotes:
            raise MapError("fields.quote requires menus.quotes")
        for row in quotes:
            if not isinstance(row, dict) or not row.get("address") or not row.get("symbol"):
                raise MapError("each menus.quotes entry needs symbol and address")
    if "logo" in fields:
        logos = menus.get("logos")
        if not isinstance(logos, list) or not logos:
            raise MapError("fields.logo requires menus.logos")
        if any(not isinstance(url, str) or not url.startswith("https://") for url in logos):
            raise MapError("menus.logos must be https URLs")
    if "feeRecipient" in fields:
        recips = menus.get("feeRecipients")
        if not isinstance(recips, list) or not recips:
            raise MapError("fields.feeRecipient requires menus.feeRecipients")
    if "exemptions" in fields:
        if not isinstance(menus.get("exemptCandidates"), list):
            raise MapError("fields.exemptions requires menus.exemptCandidates")
    if "nextBackend" in fields and not isinstance(menus.get("backends"), list):
        raise MapError("fields.nextBackend requires menus.backends")
    if "nextShots" in fields and not isinstance(menus.get("shotTiers"), list):
        raise MapError("fields.nextShots requires menus.shotTiers")
    want["maxDelaySeconds"] = int(want.get("maxDelaySeconds") or 3600)
    if not 0 < want["maxDelaySeconds"] <= 86_400:
        raise MapError("maxDelaySeconds must be 1..86400")
    return want


def map_hash(launch_map: dict[str, Any]) -> str:
    return plan_hash(load_map(launch_map))


def _check_bits(bits: Any, width: int, label: str) -> None:
    if not isinstance(bits, list) or not bits:
        raise MapError(f"{label} missing")
    seen: set[int] = set()
    for bit in bits:
        if not isinstance(bit, int) or not 0 <= bit < width or bit in seen:
            raise MapError(f"{label} is not a set of unique in-range indices")
        seen.add(bit)


def _slice(bitstring: str, indices: list[int]) -> str:
    return "".join(bitstring[i] for i in indices)


def _index(bits: str) -> int:
    return int(bits, 2)


def apply_map(bitstring: str, launch_map: dict[str, Any]) -> dict[str, Any]:
    spec = load_map(launch_map)
    spec_width = spec.get("specWidth") or spec["width"]
    if not BITSTRING_PATTERN.fullmatch(bitstring) or len(bitstring) != spec_width:
        raise MapError(f"bitstring length {len(bitstring)} does not match spec width {spec_width}")
    if spec.get("schemaVersion") == 2:
        return _apply_direct(bitstring, spec)
    launch = bitstring[spec["launchBit"]] == spec["launchWhen"]
    tax_key = _slice(bitstring, spec["taxBits"])
    delay_key = _slice(bitstring, spec["delayBits"])
    name_key = _slice(bitstring, spec["nameBits"])
    name_row = spec["names"][name_key]
    return {
        "bitstring": bitstring,
        "launch": launch,
        "reason": "launch" if launch else "map.launchBit",
        "name": name_row["name"],
        "symbol": name_row["symbol"],
        "creatorTaxBps": spec["taxTiersBps"][_index(tax_key)],
        "delaySeconds": spec["delayTiersSeconds"][_index(delay_key)],
        "buybackAndLock": False,
        "feeDestination": "creator_payout",
        "taxKey": tax_key,
        "delayKey": delay_key,
        "nameKey": name_key,
        "fromQpu": ["launch", "name", "symbol", "creatorTaxBps", "delaySeconds", "salt"],
        "classical": ["initiator", "factory", "quote", "imageUrl"],
        "encoding": "table-v1",
    }


def _from_alphabet(bits: str, alphabet: str) -> str:
    return "".join(alphabet[_index(bits[i:i + 5])] for i in range(0, len(bits), 5))


def _menu_pick(menu: list[Any], bits: str) -> Any:
    if not menu:
        raise MapError("menu is empty")
    return menu[_index(bits) % len(menu)]


def _social_char(bits: str, alphabet: str) -> str:
    if not bits or _index(bits) == 0:
        return ""
    pad = bits + "0" * ((5 - len(bits) % 5) % 5)
    return _from_alphabet(pad, alphabet)


def _apply_direct(bitstring: str, spec: dict[str, Any]) -> dict[str, Any]:
    fields = spec["fields"]
    menus = spec.get("menus") or {}
    launch_bits = _slice(bitstring, fields["launch"]["bits"])
    launch = launch_bits[-1] == fields["launch"]["when"]
    tax = min(_index(_slice(bitstring, fields["creatorTaxBps"]["bits"])), int(fields["creatorTaxBps"].get("max", 1000)))
    delay = _index(_slice(bitstring, fields["delaySeconds"]["bits"])) * int(fields["delaySeconds"].get("scale", 1))
    buyback = _slice(bitstring, fields["buyback"]["bits"])[-1] == "1"
    dest_bit = _slice(bitstring, fields["feeDestination"]["bits"])[-1]
    destination = fields["feeDestination"].get("one", "foundation") if dest_bit == "1" else fields["feeDestination"].get("zero", "creator_payout")
    from_qpu = [
        "launch", "name", "symbol", "creatorTaxBps", "delaySeconds",
        "buybackAndLock", "feeDestination", "description", "salt", "address",
    ]
    classical = ["initiator", "factory"]
    extra: dict[str, Any] = {}
    if "suffix" in fields:
        suffix_bits = _slice(bitstring, fields["suffix"]["bits"])
        suffix = format(_index(suffix_bits), "x")
        name = f"{fields['suffix'].get('namePrefix', 'QKEY')}-{suffix.upper()}"
        symbol = f"{fields['suffix'].get('symbolPrefix', 'Q')}{suffix.upper()}"
        extra["suffixBits"] = suffix_bits
        classical.extend(["quote", "imageUrl"])
    else:
        alphabet = spec["alphabet"]
        name = _from_alphabet(_slice(bitstring, fields["name"]["bits"]), alphabet)
        symbol = _from_alphabet(_slice(bitstring, fields["symbol"]["bits"]), alphabet)
    if "quote" in fields:
        quote = _menu_pick(menus["quotes"], _slice(bitstring, fields["quote"]["bits"]))
        extra["quote"] = dict(quote)
        from_qpu.append("quote")
    else:
        classical.append("quote")
    if "logo" in fields:
        extra["imageUrl"] = _menu_pick(menus["logos"], _slice(bitstring, fields["logo"]["bits"]))
        from_qpu.append("imageUrl")
    else:
        classical.append("imageUrl")
    if "launchConfigId" in fields:
        extra["launchConfigId"] = _index(_slice(bitstring, fields["launchConfigId"]["bits"]))
        from_qpu.append("launchConfigId")
    if "openingBuy" in fields:
        raw = _index(_slice(bitstring, fields["openingBuy"]["bits"]))
        extra["openingBuy"] = str(raw * int(fields["openingBuy"].get("scale", 1)))
        from_qpu.append("openingBuy")
    if "extraName" in fields:
        extra_chars = _from_alphabet(_slice(bitstring, fields["extraName"]["bits"]), spec["alphabet"])
        name = name + extra_chars
        from_qpu.append("extraName")
    if "feeRecipient" in fields:
        extra["creatorFeeRecipient"] = _menu_pick(
            menus["feeRecipients"], _slice(bitstring, fields["feeRecipient"]["bits"]),
        )
        from_qpu.append("creatorFeeRecipient")
    if "exemptions" in fields:
        mask_bits = _slice(bitstring, fields["exemptions"]["bits"])
        candidates = menus.get("exemptCandidates") or []
        extra["exemptAddresses"] = [
            candidates[i] for i, ch in enumerate(mask_bits) if ch == "1" and i < len(candidates)
        ]
        from_qpu.append("exemptAddresses")
    if "website" in fields and _slice(bitstring, fields["website"]["bits"])[-1] == "1":
        base = menus.get("websiteBase") or ""
        extra["website"] = (base.rstrip("/") + "/" + symbol.lower()) if base else ""
        from_qpu.append("website")
    if "x" in fields:
        handle = _social_char(_slice(bitstring, fields["x"]["bits"]), spec["alphabet"])
        if handle:
            extra["x"] = handle
            from_qpu.append("x")
    if "telegram" in fields:
        handle = _social_char(_slice(bitstring, fields["telegram"]["bits"]), spec["alphabet"])
        if handle:
            extra["telegram"] = handle
            from_qpu.append("telegram")
    if "nextLayers" in fields:
        extra["nextLayers"] = 1 + _index(_slice(bitstring, fields["nextLayers"]["bits"]))
        from_qpu.append("nextLayers")
    if "nextShots" in fields:
        extra["nextShots"] = _menu_pick(menus["shotTiers"], _slice(bitstring, fields["nextShots"]["bits"]))
        from_qpu.append("nextShots")
    if "nextBackend" in fields:
        extra["nextBackend"] = _menu_pick(menus["backends"], _slice(bitstring, fields["nextBackend"]["bits"]))
        from_qpu.append("nextBackend")
    extra["description"] = "measured:" + bitstring
    extra["specBitstring"] = bitstring
    delay = min(delay, int(spec.get("maxDelaySeconds") or 3600))
    if len(name) > 64 or len(symbol) > 16 or len(name) < 1 or len(symbol) < 1:
        raise MapError("decoded name/symbol outside protocol byte limits")
    return {
        "bitstring": bitstring,
        "launch": launch,
        "reason": "launch" if launch else "fields.launch",
        "name": name,
        "symbol": symbol,
        "creatorTaxBps": tax,
        "delaySeconds": delay,
        "buybackAndLock": buyback,
        "feeDestination": destination,
        "fromQpu": from_qpu,
        "classical": classical,
        "encoding": "direct-v2",
        "circuit": spec["circuit"],
        **extra,
    }


def apply_job(measurements: list[str], launch_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Every shot, in order, including skips. Holes are a filtered sequence.

    When shotsPerSpec > 1, consecutive shots are concatenated into one spec.
    Each physical shot is still listed. Salt is keccak of the concatenated bits.
    """
    spec = load_map(launch_map)
    per = int(spec.get("shotsPerSpec") or 1)
    rounds: list[dict[str, Any]] = []
    i = 0
    while i < len(measurements):
        chunk = measurements[i:i + per]
        if any(len(b) != spec["width"] for b in chunk):
            raise MapError("shot width does not match map width")
        if len(chunk) < per:
            for j, bits in enumerate(chunk):
                rounds.append({
                    "shot": i + j + 1,
                    "bitstring": bits,
                    "launch": False,
                    "reason": "incomplete_spec",
                    "name": "",
                    "symbol": "",
                    "creatorTaxBps": 0,
                    "delaySeconds": 0,
                })
            break
        spec_bits = "".join(chunk)
        decision = apply_map(spec_bits, spec)
        for j, bits in enumerate(chunk):
            row = dict(decision)
            row["shot"] = i + j + 1
            row["bitstring"] = bits
            row["specBitstring"] = spec_bits
            row["specRole"] = "head" if j == 0 else "cont"
            rounds.append(row)
        i += per
    return rounds


def circuit_angles(angle_seed: str, count: int) -> list[float]:
    """Public, reproducible RY/RZ angles. Part of the hashed map, not a secret."""
    import math

    out: list[float] = []
    for i in range(count):
        digest = keccak256(f"{angle_seed}:{i}".encode("utf-8"))
        n = int(digest, 16) % 1_000_000
        out.append((n / 1_000_000.0) * 2 * math.pi)
    return out


def tally(rounds: list[dict[str, Any]]) -> dict[str, int]:
    heads = [row for row in rounds if row.get("specRole", "head") == "head"]
    launched = sum(1 for row in heads if row["launch"])
    return {
        "measured": len(rounds),
        "specs": len(heads),
        "launched": launched,
        "skipped": len(heads) - launched,
    }
