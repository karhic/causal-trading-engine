from causaltrader import Bar, FuturesChain, Strategy, TargetWeight

class CommodityBasisShape(Strategy):
    name = "commodity_basis_shape"
    version = "0-example"
    def __init__(self, roots=("CL","GC","HG","NG"), k=1, gross=1.0): self.roots,self.k,self.gross=tuple(roots),int(k),float(gross)
    def _weekly_return(self, ctx, contract):
        bars=[e.payload for e in ctx.data.history("market.bar.1d",contract,count=6) if isinstance(e.payload,Bar)]
        return None if len(bars)<2 else bars[-1].close/bars[0].close-1.0
    def on_event(self,ctx,event):
        if event.dataset != "calendar.weekly_rebalance": return ()
        scored=[]; fronts=[]
        for root in self.roots:
            ce=ctx.data.latest("futures.chain",root)
            if ce is None or not isinstance(ce.payload,FuturesChain): continue
            f1,f2=ce.payload.nth(1),ce.payload.nth(2); r1,r2=self._weekly_return(ctx,f1),self._weekly_return(ctx,f2)
            if r1 is None or r2 is None: continue
            fronts.append(f1); scored.append((r1-r2,root,f1))
        if len(scored)<2*self.k: return ()
        scored.sort(); longs={x[2] for x in scored[:self.k]}; shorts={x[2] for x in scored[-self.k:]}; per=self.gross/(2*self.k)
        targets={i:0.0 for i in set(ctx.state.get("commodity_fronts",[]))|set(fronts)}
        for i in longs: targets[i]=per
        for i in shorts: targets[i]=-per
        ctx.state["commodity_fronts"]=sorted(fronts)
        return tuple(TargetWeight(i,w,reason="weekly F1-F2 cross-sectional rank") for i,w in sorted(targets.items()))
