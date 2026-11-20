import pandas as pd
d='/mnt/project-files/'
c=pd.read_csv(d+'dft-road-casualty-statistics-collision-2025.csv',dtype=str)
k=pd.read_csv(d+'dft-road-casualty-statistics-casualty-2025.csv',dtype=str)
v=pd.read_csv(d+'dft-road-casualty-statistics-vehicle-2025.csv',dtype=str)
print(pd.crosstab(v.vehicle_manoeuvre_historic,v.vehicle_manoeuvre).to_string())
MC=['2','3','4','5','23','97']
for name,fs in {'Cleveland+Durham':['17','11'],'NWales+Gwent':['60','61'],'Leics':['33'],'Glos':['53'],'NWales+Gwent+Cleveland':['60','61','17']}.items():
    s=c[c.police_force.isin(fs)].copy(); ids=set(s.collision_index)
    ks=k[k.collision_index.isin(ids)]; vs=v[v.collision_index.isin(ids)]
    s['ksi']=s.collision_severity.isin(['1','2'])
    ksi=set(s[s.ksi].collision_index)
    vru=set(ks[ks.casualty_type.isin(['0','1']+MC)].collision_index)
    out=dict(n=len(s),veh=len(vs),cas=len(ks),fatal=(s.collision_severity=='1').sum(),ksi=len(ksi),LAs=s.local_authority_ons_district.nunique(),LSOAs=s.lsoa_of_accident_location.nunique(),lsoa_missing=(s.lsoa_of_accident_location=='-1').sum())
    out['CQ1_vru_coll']=len(vru); out['vru_ksi_coll']=len(vru&ksi)
    lk=s[s.ksi].groupby('lsoa_of_accident_location').size()
    out['lsoa>=2']=(lk>=2).sum(); out['lsoa>=3']=(lk>=3).sum(); out['lsoa>=4']=(lk>=4).sum()
    la=s[s.ksi].groupby('local_authority_ons_district').size().sort_values(ascending=False)
    out['LA_ksi']=la.to_dict()
    awi=s[s.ksi & s.first_road_class.isin(['2','3']) & s.road_surface_conditions.isin(['2','4'])]
    out['CQ3']=awi.groupby('local_authority_ons_district').size().sort_values(ascending=False).head(6).to_dict(); out['CQ3_ice']=(awi.road_surface_conditions=='4').sum()
    out['CQ4_ped_ksi']=((ks.casualty_class=='3')&ks.casualty_severity.isin(['1','2'])).sum()
    out['CQ5_dark_ksi']=s[s.ksi&s.light_conditions.isin(['4','5','6','7'])].shape[0]
    cyc=ks[(ks.casualty_type=='1')&ks.casualty_severity.isin(['1','2'])]; out['CQ6_cyc_ksi']=len(cyc)
    yd=set(vs[vs.age_of_driver.astype(int).between(17,24)].collision_index); out['CQ7_young_ksi']=len(yd&ksi)
    ch=ks[ks.age_band_of_casualty.isin(['1','2','3'])&ks.casualty_severity.isin(['1','2'])]; out['CQ8_child_ksi']=len(ch); out['CQ8_cls']=ch.casualty_class.value_counts().to_dict()
    fast=set(s[s.speed_limit.astype(int)>=50].collision_index)
    mc=set(ks[ks.casualty_type.isin(MC)&ks.casualty_severity.isin(['1','2'])].collision_index); out['CQ9']=len(mc&fast)
    out['CQ12']=s[s.ksi].junction_detail.value_counts().to_dict()
    out['CQ11_roadtype']=s[s.ksi].road_type.value_counts().to_dict()
    for kk,vv in out.items(): print(name,kk,vv)
    print()
