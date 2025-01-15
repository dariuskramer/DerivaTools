#!/usr/bin/env python
# coding: utf-8

import ib_async
import datetime
import logging
from math import isnan

ib = ib_async.IB()

try:
    ib.connect(port=7496, readonly=True)
    print("Connecté à Interactive Brokers")
except Exception as e:
    print(f"Erreur de connexion : {e}")

logging.basicConfig(level=logging.INFO)

# Créer le contrat SPX et le qualifier
spx = ib_async.Index('SPX', 'CBOE')
ib.qualifyContracts(spx)
logging.info('Contract qualified')

# Utiliser des données de marché live ou en décalé de 15min si indisponible en live
# Voir: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#delayed-market-data
ib.reqMarketDataType(3)

# Récupérer les données de la chaîne d'options
logging.info('Fetch option chains')
chains = ib.reqSecDefOptParams(spx.symbol, '', spx.secType, spx.conId)

# Il existe 2 contrats pour les options du SPX:
#   - SPX  => contrats mensuelles qui expire typiquement le 3ème vendredi du mois
#   - SPXW => contrats 0dte
# Si un contrat SPX expire aujourd'hui on choisit celui-ci, sinon on prend le contrat SPXW 0dte
[chain] = [c for c in chains if c.tradingClass == 'SPX' and c.exchange == 'SMART']
today_expiry = datetime.datetime.now().strftime('%Y%m%d')
next_contract_expiry = sorted(chain.expirations)[0]

if today_expiry == next_contract_expiry:
    # contrat SPX: expiration mensuelle
    pass
else:
    # contrat SPXW: expiration 0dte
    [chain] = [c for c in chains if c.tradingClass == 'SPXW' and c.exchange == 'SMART'] 
    next_contract_expiry = sorted(chain.expirations)[0]

logging.info(f'Selected contract type: {chain.exchange} {chain.tradingClass} {next_contract_expiry}')

# Limitation du nombres de strikes qu'on va récupérer (+- 2% du prix actuel ou de cloture)
logging.info(f'Fetching current, or close, price')
[ticker] = ib.reqTickers(spx)
spxValue = ticker.close if isnan(ticker.last) else ticker.last
strikes = [strike for strike in chain.strikes if abs(strike - spxValue) <= spxValue * 0.02]
logging.info(f'Selected strikes range: [{strikes[0]:.0f}..{strikes[-1]:.0f}]')

# Création des contrats d'Options pour l'échéance
call_contracts = [ib_async.Option('SPX', next_contract_expiry, strike, 'C', chain.exchange, tradingClass=chain.tradingClass)
         for strike in strikes]
put_contracts = [ib_async.Option('SPX', next_contract_expiry, strike, 'P', chain.exchange, tradingClass=chain.tradingClass)
         for strike in strikes]

ib.qualifyContracts(*call_contracts)
ib.qualifyContracts(*put_contracts)

# On récupère les données de la chaîne d'options
logging.info(f'Fetching option chain data for each strikes')
calls = ib.reqTickers(*call_contracts)
puts = ib.reqTickers(*put_contracts)

# Calcul du Risk Reversal Skew 25 Delta
logging.info(f'Calculating RR Skew 25 Delta')
call_25delta = sorted(calls, key=lambda call: abs(0.25 - call.modelGreeks.delta))[0]
put_25delta = sorted(puts, key=lambda put: abs(0.25 + put.modelGreeks.delta))[0]

output = f"""\
# CALL 25 Delta:
\t- Strike {call_25delta.contract.strike:.0f}
\t- Delta {round(call_25delta.modelGreeks.delta, 4)}
\t- Ask price {call_25delta.ask}
\t- IV {round(call_25delta.modelGreeks.impliedVol, 4):.2%}

# PUT 25 Delta:
\t- Strike {put_25delta.contract.strike:.0f}
\t- Delta {round(put_25delta.modelGreeks.delta, 4)}
\t- Ask price {put_25delta.ask}
\t- IV {round(put_25delta.modelGreeks.impliedVol, 4):.2%}
"""
print(output)

# Calcul du Risk Reversal Skew 15 Delta
logging.info(f'Calculating RR Skew 15 Delta')
call_15delta = sorted(calls, key=lambda call: abs(0.15 - call.modelGreeks.delta))[0]
put_15delta = sorted(puts, key=lambda put: abs(0.15 + put.modelGreeks.delta))[0]

output = f"""\
# CALL 15 Delta:
\t- Strike {call_15delta.contract.strike:.0f}
\t- Delta {round(call_15delta.modelGreeks.delta, 4)}
\t- Ask price {call_15delta.ask}
\t- IV {round(call_15delta.modelGreeks.impliedVol, 4):.2%}

# PUT 15 Delta:
\t- Strike {put_15delta.contract.strike:.0f}
\t- Delta {round(put_15delta.modelGreeks.delta, 4)}
\t- Ask price {put_15delta.ask}
\t- IV {round(put_15delta.modelGreeks.impliedVol, 4):.2%}
"""
print(output)
