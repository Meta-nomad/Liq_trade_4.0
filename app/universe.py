"""Public-data eligibility, not fraud detection. Unknown metadata fails closed."""
import logging,time
from .config import DEFAULT_SYMBOLS
LOG=logging.getLogger(__name__)

def exclusion(meta,ticker,now):
    if not meta or meta.get('status')!='Trading' or meta.get('contractType')!='LinearPerpetual' or meta.get('quoteCoin')!='USDT':
        return 'inactive_or_wrong_contract'
    if meta.get('isPreListing') or float(meta.get('deliveryTime') or 0)>0:return 'prelisting_or_delisting'
    launch=float(meta.get('launchTime') or 0)/1000
    if launch<=0 or now-launch<180*86400:return 'younger_than_180d_or_unknown'
    if float(ticker.get('turnover24h') or 0)<10_000_000:return 'turnover_below_10m'
    bid=float(ticker.get('bid1Price') or 0);ask=float(ticker.get('ask1Price') or 0)
    if bid<=0 or ask<=bid or (ask-bid)/((ask+bid)/2)*10000>10:return 'spread_above_10bps_or_unknown'
    return ''

async def screen(symbols):
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        async def get(path,params):
            r=await client.get('https://api.bybit.com'+path,params=params);r.raise_for_status();d=r.json()
            if d.get('retCode')!=0:raise RuntimeError('Universe metadata rejected by exchange')
            return d['result']
        metas={};cursor='';seen=set()
        while True:
            d=await get('/v5/market/instruments-info',dict(category='linear',limit=1000,cursor=cursor))
            metas.update({x['symbol']:x for x in d['list']});cursor=d.get('nextPageCursor','')
            if not cursor:break
            if cursor in seen:raise RuntimeError('Repeated universe pagination cursor')
            seen.add(cursor)
        d=await get('/v5/market/tickers',{'category':'linear'});ticks={x['symbol']:x for x in d['list']}
    out=[];now=time.time()
    for s in dict.fromkeys(symbols):
        reason='outside_reviewed_candidate_list' if s not in DEFAULT_SYMBOLS else exclusion(metas.get(s.replace('_',''),{}),ticks.get(s.replace('_',''),{}),now)
        LOG.info('UNIVERSE symbol=%s result=%s',s,reason or 'ELIGIBLE_BYBIT')
        if not reason:out.append(s)
    if not out:raise RuntimeError('No eligible contracts; refusing to trade')
    return tuple(out)
