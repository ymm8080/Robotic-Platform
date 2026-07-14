"""å®‰å…¨ PLC æŽ¥å£ â€” æ³•å¾‹ç¡¬ä¸‹é™çš„æƒå¨å¯„å­˜å™¨ (v7 Phase 4 task 5).

ç™½çš®ä¹¦ Â§2.3 / é“å¾‹äºŒ (ç‰©ç†å±‚ä¸ºæœ€åä¹°å•): ç¡¬ä¸‹é™ S_min â‰¥ 1.5 m
(GB/T 10827.1-2014) å†™å…¥å®‰å…¨ PLC, ä»»ä½•è½¯ä»¶å±‚æ— æƒè¦†ç›–.

æ­¤å‰ ``SafetyConfig.hard_floor`` æ˜¯ä¸€ä¸ª *å£°ç§°* é•œåƒ PLC å¯„å­˜å™¨çš„å†»ç»“é…ç½®å€¼,
ä½†å¹¶æ— çœŸå®ž PLC å¼ºåˆ¶å®ƒ â€” è½¯ä»¶è‹¥è¯¯æ”¹é…ç½®å³å¯é™é»˜ lowering. æœ¬æ¨¡å—è¡¥ä¸Š"è½ PLC
æŽ¥å£"çš„ç¼ºå£: ``SafetyPlc`` ä»£è¡¨å®‰å…¨ PLC çš„æƒå¨å¯„å­˜å™¨, è½¯ä»¶åªèƒ½ *æŠ¬é«˜* ç”³è¯·
ä¸‹é™, æ°¸ä¸èƒ½ä½ŽäºŽå¯„å­˜å™¨æ³•å®šå€¼.

# ponytail: ä¸å¼•å…¥çœŸå®ž PLC é©±åŠ¨ (ç¡¬ä»¶æœªå®š) â€” ä»…å»ºæ¨¡å…¶æƒå¨å¯„å­˜å™¨è¯­ä¹‰.
# å‡çº§è·¯å¾„: æŽ¥çœŸå®žå®‰å…¨ PLC (Modbus/EtherCAT) è¯»å¯„å­˜å™¨å€¼, enforce() ä¸å˜.
"""

from __future__ import annotations

from dataclasses import dataclass

LEGAL_HARD_FLOOR_M = 1.5  # GB/T 10827.1-2014 æ³•å®šç¡¬ä¸‹é™
_DEMO_HARD_FLOOR_M = 0.5  # DEMO æ¨¡å¼å¯„å­˜å™¨ (é”€å”®æ¼”ç¤º, æ˜¾å¼é™çº§)


@dataclass(frozen=True)
class PlcFloorViolation:
    """è½¯ä»¶å°è¯• lowering å¯„å­˜å™¨æ³•å®šå€¼çš„å®¡è®¡è®°å½•."""

    requested: float
    legal_floor: float
    enforced: float


class SafetyPlc:
    """å®‰å…¨ PLC æƒå¨ç¡¬ä¸‹é™å¯„å­˜å™¨.

    è½¯ä»¶åªè¯»å¯„å­˜å™¨å€¼; ``enforce`` æŠŠè½¯ä»¶ç”³è¯·çš„ä¸‹é™é’³åˆ° â‰¥ å¯„å­˜å™¨æ³•å®šå€¼.
    ä»»ä½• lowering å°è¯•è¢«æ‹’ç»å¹¶è®°å½• (ä¸æŠ›å¼‚å¸¸ â€” å®‰å…¨è·¯å¾„ä¸å¾—å› å®¡è®¡è€Œä¸­æ–­).
    """

    def __init__(self, hard_floor: float = LEGAL_HARD_FLOOR_M) -> None:
        if hard_floor < 0:
            raise ValueError("safety PLC hard floor must be non-negative")
        self._hard_floor = hard_floor
        self._violations: list[PlcFloorViolation] = []

    @property
    def hard_floor(self) -> float:
        """å¯„å­˜å™¨æ³•å®šç¡¬ä¸‹é™ (è½¯ä»¶ä¸å¯ lowering)."""
        return self._hard_floor

    @classmethod
    def for_demo(cls) -> SafetyPlc:
        """DEMO æ¨¡å¼å¯„å­˜å™¨ (0.5m, æ˜¾å¼é™çº§ â€” ä»…é”€å”®æ¼”ç¤º)."""
        return cls(_DEMO_HARD_FLOOR_M)

    def enforce(self, requested_floor: float) -> float:
        """é’³åˆ¶è½¯ä»¶ç”³è¯·çš„ä¸‹é™åˆ° â‰¥ å¯„å­˜å™¨æ³•å®šå€¼.

        è½¯ä»¶å¯æŠ¬é«˜ (è¿”å›ž requested), ä¸å¯ lowering (è¿”å›žæ³•å®šå€¼å¹¶è®°å®¡è®¡).
        """
        if requested_floor < self._hard_floor:
            self._violations.append(
                PlcFloorViolation(
                    requested=requested_floor,
                    legal_floor=self._hard_floor,
                    enforced=self._hard_floor,
                )
            )
            return self._hard_floor
        return requested_floor

    def violations(self) -> tuple[PlcFloorViolation, ...]:
        """è¿”å›žè‡³ä»Šè¢«æ‹’ç»çš„ lowering å°è¯• (å®¡è®¡ / åˆè§„å–è¯)."""
        return tuple(self._violations)


# â”€â”€ è‡ªæ£€ (DoD: è½¯ä»¶æ— æ³• lowering PLC æ³•å®šä¸‹é™) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _self_test() -> None:
    plc = SafetyPlc()  # é»˜è®¤ 1.5m æ³•å®š
    assert plc.hard_floor == 1.5
    # æŠ¬é«˜å…è®¸
    assert plc.enforce(2.0) == 2.0
    # lowering è¢«æ‹’, é’³å›žæ³•å®šå€¼
    assert plc.enforce(0.5) == 1.5
    assert plc.enforce(0.0) == 1.5
    assert len(plc.violations()) == 2, "two lowering attempts recorded"
    # DEMO å¯„å­˜å™¨æ˜¾å¼é™çº§
    assert SafetyPlc.for_demo().hard_floor == 0.5
    print("OK: safety PLC â€” software cannot lower legal hard floor (1.5m)")


if __name__ == "__main__":
    _self_test()
