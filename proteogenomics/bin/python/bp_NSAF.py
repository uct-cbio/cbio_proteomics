#!/usr/bin/env python

import pandas as pd
import sys
from collections import defaultdict
from Bio import SeqIO

data = pd.read_csv(sys.argv[1])


data = data[[i for i in data.columns if not i.startswith('Untitled: ')]]
sample_cols = [i for i in data.columns if i.startswith('Sample ')]

nsafcols = []

for col in sample_cols:
    sample = col.split(' (msms)')[0]
    nsafcol = sample + ' (NSAF)'
    data[nsafcol] = data[col]/data['SequenceLength']
    data[nsafcol] = data[nsafcol]/data[nsafcol].sum()
    nsafcols.append(nsafcol)

data['Summed NSAF'] = data[nsafcols].sum(axis=1)

data = data.sort_values(by='Summed NSAF', ascending = False)
data = data.reset_index()
del data['index']

data['MSMS_list'] = data['MSMS'].apply( lambda x : x.split('\n'))
all_msms = data['MSMS_list'].tolist()
del data['MSMS_list']

msms_set = set()
all_cum= []
for msms in all_msms:
    msms_set.update(msms)
    all_cum.append(len(msms_set))

msms_set_len = len(msms_set)

data['CumulativeMSMSCount'] = pd.Series(all_cum)
data['CumulativeMSMSPercentage'] = data['CumulativeMSMSCount'] / msms_set_len * 100.0

prefix = sys.argv[2].split('.csv')[0]
data.to_csv(sys.argv[2])

data_100 = data[data['CumulativeMSMSPercentage'] <= 100]
records = data_100['Records'].tolist()
w= open(prefix +'_100perc_msmms_mapped.fasta','w')
w.write('\n'.join(records))
w.close()

data_99 = data[data['CumulativeMSMSPercentage'] <= 99]
records = data_99['Records'].tolist()
w= open(prefix +'_99perc_msmms_mapped.fasta','w')
w.write('\n'.join(records))
w.close()

data_95 = data[data['CumulativeMSMSPercentage'] <= 95]
records = data_95['Records'].tolist()
w= open(prefix +'_95perc_msmms_mapped.fasta','w')
w.write('\n'.join(records))
w.close()

data_90 = data[data['CumulativeMSMSPercentage'] <= 90]
records = data_90['Records'].tolist()
w= open(prefix +'_90perc_msmms_mapped.fasta','w')
w.write('\n'.join(records))
w.close()

data_80 = data[data['CumulativeMSMSPercentage'] <= 80]
records = data_80['Records'].tolist()
w= open(prefix +'_80perc_msmms_mapped.fasta','w')
w.write('\n'.join(records))
w.close()




