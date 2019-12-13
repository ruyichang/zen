#ifndef GTESTUTILS_H
#define GTESTUTILS_H

#include <primitives/transaction.h>

namespace gtestUtils {

CMutableTransaction populateTx(int txVersion, const uint256 & newScId = uint256S("0"), const CAmount & fwdTxAmount = CAmount(0));

void signTx(CMutableTransaction& mtx);

CTransaction createSidechainTxWith(const uint256 & newScId, const CAmount & fwdTxAmount);

CTransaction createFwdTransferTxWith(const uint256 & newScId, const CAmount & fwdTxAmount);

CTransaction createSidechainTxWithNoFwdTransfer(const uint256 & newScId);

CTransaction createTransparentTx(bool ccIsNull);

CTransaction createSproutTx(bool ccIsNull);

void extendTransaction(CTransaction & tx, const uint256 & scId, const CAmount & amount);

};

#endif
