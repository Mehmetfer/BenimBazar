/// User-facing copy for Change Chain proposal engine vs settlement.
///
/// Engine phase is always proposal/consent only. Settlement / Asset Lock is
/// NOT_IMPLEMENTED — never present ACCEPTED consent as completed transfer.
class ChainEngineUx {
  static const settlementStatus = 'NOT_IMPLEMENTED';
  static const assetLockStatus = 'NOT_IMPLEMENTED';
  static const enginePhase = 'PROPOSAL_ONLY';

  static String featureDisabledMessage() =>
      'Çoklu takas zinciri şu an kapalı. Doğrudan takas kullanabilirsiniz. '
      'Settlement / Asset Lock henüz yok ($settlementStatus).';

  static String proposalOnlyMessage() =>
      'Zincir önerisi ve onay kaydedilir; mülkiyet transferi yok '
      '($settlementStatus).';

  static String settlementNotImplementedMessage() =>
      'Asset Lock settlement $settlementStatus — onay, takas tamamlanması değildir.';

  static String takasLabel({
    required bool chainOptIn,
    required String tradePreference,
    bool chainEngineEnabled = false,
  }) {
    final pref = tradePreference.toUpperCase();
    if (chainOptIn && pref == 'CHAIN_ALLOWED') {
      if (!chainEngineEnabled) {
        return 'ZİNCİR ADAYI · MOTOR KAPALI';
      }
      return 'ZİNCİR AÇIK · SETTLEMENT YOK';
    }
    if (pref == 'DIRECT_ONLY') return 'DOĞRUDAN';
    return 'TAKAS';
  }

  static String takasAttributeValue({
    required bool chainOptIn,
    required String tradePreference,
    bool chainEngineEnabled = false,
  }) {
    final pref = tradePreference.toUpperCase();
    if (chainOptIn && pref == 'CHAIN_ALLOWED') {
      if (!chainEngineEnabled) {
        return 'EVET · ZİNCİR KAPALI (FLAG OFF)';
      }
      return 'EVET · ZİNCİR AÇIK · $settlementStatus';
    }
    return 'EVET · DOĞRUDAN';
  }
}
