import pandas as pd
d='/mnt/project-files/'
c=pd.read_csv(d+'dft-road-casualty-statistics-collision-2025.csv',dtype=str)
k=pd.read_csv(d+'dft-road-casualty-statistics-casualty-2025.csv',dtype=str)
v=pd.read_csv(d+'dft-road-casualty-statistics-vehicle-2025.csv',dtype=str)
s=c[c.police_force.isin(['60','61'])].copy(); ids=set(s.collision_index)
ks=k[k.collision_index.isin(ids)]; vs=v[v.collision_index.isin(ids)]
s['ksi']=s.collision_severity.isin(['1','2'])
MC=['2','3','4','5','23','97']
vru=set(ks[ks.casualty_type.isin(['0','1']+MC)].collision_index)
lk=s[s.ksi].groupby('lsoa_of_accident_location').size()
hra=lk[lk>=3]
print('HRA LSOAs',len(hra), hra.value_counts().sort_index().to_dict())
sub=s[s.ksi & s.lsoa_of_accident_location.isin(hra.index)]
print('CQ13 KSI in HRA',len(sub),'VRU',sub.collision_index.isin(vru).sum())
print('HRA by LA', sub.drop_duplicates('lsoa_of_accident_location').local_authority_ons_district.value_counts().to_dict())
print('HRA by force', sub.drop_duplicates('lsoa_of_accident_location').police_force.value_counts().to_dict())
cyc=ks[(ks.casualty_type=='1')&ks.casualty_severity.isin(['1','2'])]
m=cyc.merge(vs,on='collision_index',suffixes=('_c','_v'))
m=m[m.vehicle_reference_c!=m.vehicle_reference_v]
print('CQ6 other veh', m.vehicle_type.value_counts().to_dict(), 'single-vehicle cyclist KSI', len(set(cyc.collision_index)-set(m.collision_index)))
ped=ks[(ks.casualty_class=='3')&ks.casualty_severity.isin(['1','2'])].merge(vs,on=['collision_index','vehicle_reference'])
print('CQ4 manoeuvre', ped.vehicle_manoeuvre.value_counts().to_dict())
print('CQ4 light', s[s.collision_index.isin(ped.collision_index)].light_conditions.value_counts().to_dict())
print('dark/daylight KSI by force', s[s.ksi].assign(dark=s.light_conditions.isin(['4','5','6','7'])).groupby(['police_force','dark']).size().to_dict())
print('light -1 in sample',(s.light_conditions=='-1').sum(), 'surface -1/9', s.road_surface_conditions.isin(['-1','9']).sum(), 'age -1', (vs.age_of_driver=='-1').sum(), 'age band -1 cas',(ks.age_band_of_casualty=='-1').sum())
print('casualty type 33 in sample',(ks.casualty_type=='33').sum())
print('vehicle_ref linkage ok', ks.merge(vs,on=['collision_index','vehicle_reference']).shape[0], len(ks))
f=s[(s.collision_severity=='1')&s.collision_index.isin(vru)]
print('fatal VRU', len(f), f.collision_index.head(5).tolist())
print('LSOA->LA unique', (s.groupby('lsoa_of_accident_location').local_authority_ons_district.nunique()>1).sum())
print('first_road_class A in sample', s.first_road_class.isin(['2','3']).sum(), 'wet', (s.road_surface_conditions=='2').sum(),'ice',(s.road_surface_conditions=='4').sum())
