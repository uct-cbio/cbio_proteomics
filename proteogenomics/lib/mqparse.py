#!/usr/bin/python
import drive
import Bio; from Bio import SeqIO
from Bio.SeqRecord import SeqRecord
from Bio.Seq import Seq, translate
import pandas as pd
from pandas import DataFrame,  Series
import json
import collections; from collections import defaultdict
import tempfile
from matplotlib_venn import venn3, venn2, venn3_circles, venn2_circles
from matplotlib import pyplot as plt
import shutil
import numpy as np
import algo
import time
import blast
import StringIO
import re

def name_dct():
    names = {'sf_novel_m':'Six Frame Novel Only\n(M start)',
            'sf_novel':'Six Frame Novel Only',
            'ref_prot_alt':'Reference Proteome\n(Embl CDS Start AA Alternative)',
            'ref_prot':'Reference Proteome',
            'alt_gms':'GenemarkS Predictions\n(M start)',
            'gms':'GenemarkS Predictions',
            'raw_sf':'Six Frame Translation',
            'alt_sf':'Six Frame Translation\n(M start)'}
    return names

def split_join(value):
    value = value.split(';')
    value = '\n'.join(value)
    return value

def param_table(mapping_dct):
    names = name_dct()
    sum_dct = defaultdict()
    for i in mapping_dct:
        if (i != 'mapping') and (i != 'flatfile'):
            tup =mapping_dct[i]
            fasta = list(SeqIO.parse(tup[0],'fasta'))
            sum = pd.read_csv(tup[1]+'/parameters.txt', sep=None, engine='python')
            sum= sum.set_index('Parameter')
            sum.rename(columns ={'Value':i}, inplace= True)
            sum_dct[i]=sum
            
    summary = pd.concat(sum_dct.values(), axis =1)

    summary = summary[['raw_sf', 
        'alt_sf', 
        'ref_prot', 
        'gms', 
        'alt_gms',
        'sf_novel',
        'sf_novel_m',
        'ref_prot_alt']]
    summary.rename(columns=names, inplace=True)
    return summary

def summary_table(mapping_dct):
    names = name_dct()
    sum_dct = defaultdict()
    for i in mapping_dct:
        if (i != 'mapping') and (i != 'flatfile'):
            tup =mapping_dct[i]
            fasta = list(SeqIO.parse(tup[0],'fasta'))
            sum = pd.read_csv(tup[1]+'/summary.txt', sep=None, engine='python')
            sum['Fasta DB Size'] = len(fasta)
            sum= sum.set_index('Raw file')
            params = sum[['Enzyme', 
                        'Enzyme mode',
                        'Enzyme first search',
                        'Enzyme mode first search',
                        'Use enzyme first search',
                        'Variable modifications',
                        'Variable modifications first search',
                        'Use variable modifications first search',
                        'Multiplicity',
                        'Max. missed cleavages']].fillna(method='pad')
            
            params['Enzyme'] = params['Enzyme'].apply(split_join)
            params['Variable modifications'] = params['Variable modifications'].apply(split_join)
            params = params.loc['Total',:].dropna(how='any')
            series =  sum.loc['Total',:].dropna(how='any')
            params = params.append(series)
            params.name=i
         
            sum_dct[i]=params
    summary = pd.concat(sum_dct.values(), axis =1)
    summary = summary[['raw_sf', 
        'alt_sf', 
        'ref_prot', 
        'gms', 
        'alt_gms',
        'sf_novel',
        'sf_novel_m',
        'ref_prot_alt']]

    summary.rename(columns=names, inplace=True)
    return summary

def verify(df):    #check that the unique peptide occurred in more than onereplicate
    df1 =df.copy()
    columns = []
    for i in df1.columns:
        if i.startswith('Unique peptides '):
            columns.append(i)
    return columns

def peptides(path):
    pep_dct = {}
    unique_pep_dct = {}
    peptides_path = path +'/peptides.txt'
    peps = pd.read_csv(peptides_path, sep=None, engine='python')
    peps = peps[peps['PEP'] < 0.01]
    for row in peps.iterrows():
        id_count  = 0
        for j in peps.columns:
            if j.startswith('Identification type'):
                if (row[1][j] == 'By MS/MS'):
                    id_count += 1
        peps.loc[row[0], 'Number of Replicates'] = id_count
    peps = peps[peps['Number of Replicates'] > 1 ]
    unique_peps = peps[peps['Unique (Groups)']=='yes']
    for row in peps.iterrows():
        index = row[0]
        sequence = row[1]['Sequence']
        if row[1]['Unique (Proteins)'] =='yes':
            unique_pep_dct[index] = sequence
        else:
            pep_dct[index] = sequence
    return pep_dct, unique_pep_dct

def evidence_table(txt_path, i):
    evp = txt_path +'/evidence.txt'
    ev = pd.read_csv(evp, sep =None, engine='python')
    ev = ev[ev['PEP'] < 0.01]
    sequences = list(set(ev['Sequence'].values))
    seq_dct = {}
    for item in sequences:
        num = len(set(ev[ev['Sequence'] == item]['Experiment']))
        seq_dct[item] = num
    for row in ev.iterrows():
        seq = row[1]['Sequence']
        reps = seq_dct[seq]
        ev.loc[row[0], 'Number of Replicates'] = reps
    ev = ev[ev['Number of Replicates'] > 1]
    return ev

def filteredPG(path, name):   #path to txt, returns filtered
    prot_path = path+'/proteinGroups.txt'
    pg = pd.read_csv(prot_path, sep=None, engine='python')
    potential_contaminants = pg[pg['Potential contaminant']=='+']
    reverse = pg[pg['Reverse'].notnull()]
    if len(reverse)>0:
        reverse = reverse[reverse['Reverse']=='+']
    pg1 = pg[(pg['Reverse'].isnull()) & (pg['Potential contaminant'].isnull())]
    pg1_err = pg1[(pg1['Protein IDs'].str.startswith('REV'))|(pg1['Protein IDs'].str.startswith('CON'))]
    pg1 = pg1[~((pg1['Protein IDs'].str.startswith('REV'))|(pg1['Protein IDs'].str.startswith('CON')))]
    pg1_single = pg1[pg1['Number of proteins'] == 1]
    pg1_multiple = pg1[pg1['Number of proteins']>1]
    
    sum = pd.Series([
        len(pg1),
        len(pg1_single), 
        len(pg1_multiple), 
        len(potential_contaminants),
        len(reverse),
        len(pg)])
    sum.name = name
    sum.index = ['Protein Groups (filtered)',
                'Protein Groups with one member (filtered)',
                'Protein Groups with multiple members (filtered)',
                'Potential Contaminant Protein Groups',
                'Reversed Sequence Hits Protein Groups',
                'Total Protein Groups (unfiltered)']

    return pg1, pg1_multiple, sum

def fasta_dct(path):
    rec_dct = {}
    dct = {}
    ls = list(SeqIO.parse(path, 'fasta'))
    for i in ls:
        id = i.id
        if id not in dct:
            dct[id]=str(i.seq)
            rec_dct[id] = i
    return dct, rec_dct

def add_fasta(df,  fasta_dct, peptide_dct, unique_peps,  db):
    new_df = df.copy()
    fasta_db = fasta_dct[db]
    peptide_db = peptide_dct[db]
    unique_db = unique_peps[db]
    
    old_cols = new_df.columns.tolist()
    prot_cols = []
    peptide_cols = ['Unique_Peptides', 'Non_Unique_Peptides']
    analysis_cols = ['Start_Sites_Found']
    for row in new_df.iterrows():
        index = row[0]
        protein_ids = row[1]['Protein IDs'].split(';')
        peptides = [peptide_db[int(i)] for i in row[1]['Peptide IDs'].split(';') if int(i) in peptide_db]
        unique_peptides=[unique_db[int(i)] for i in row[1]['Peptide IDs'].split(';') if int(i) in unique_db]
        trie = algo.trie_graph(peptides + unique_peptides)
        count = 1
        starts_found = []
        for i in protein_ids:
            colname='Protein_ID_{}'.format(count)
            if colname not in prot_cols:
                prot_cols.append(colname)
            if i in fasta_db:
                rec = fasta_db[i]
                new_id = rec.id
                new_description = rec.description
                new_seq = rec.seq
                positions = algo.trie_matching(trie, new_seq)
                if len(positions) > 0:
                    if positions[0] == 0:
                        starts_found.append(colname)
                new_seq = Seq(algo.trie_upper(trie, str(new_seq)))
                new_rec = SeqRecord(seq = new_seq, id = new_id, description = new_description)
                new_df.loc[index, colname] = new_rec.format('fasta')
            else:
                new_df.loc[index,colname]=i
            count += 1
        new_df.loc[index, 'Unique_Peptides'] = '\n'.join(unique_peptides)
        new_df.loc[index, 'Non_Unique_Peptides'] ='\n'.join(peptides)
        new_df.loc[index, 'Start_Sites_Found']='\n'.join(starts_found)
        new_cols = prot_cols + peptide_cols +  old_cols
        new_df = new_df[new_cols]
    return new_df

def cleavage_site(peptide, fasta_record, genome):
    seq = str(fasta_record.seq)
    description = fasta_record.description
    position = seq.find(peptide) * 3
    coords = [j.split('|') for j in description.split() if (j.startswith('(+)') or j.startswith('(-)'))]
    coords =  [item for sublist in coords for item in sublist] 
    cleavage_pep = True
    if len(coords) != 0:
        cleavage_pep = False
    for coord in coords:
        try:
            strand = coord.split(')')[0][1:]
            datum = coord.split(')')[1].split(':')
        except: 
            strand = coord.split(')')[0][1:]
            datum = coord.split(')')[1].split(':')
        start = int(datum[0])
        end = int(datum[1])
        cleavage = ['R','K']
        if strand == '-':
            pep_pos = end - position
            assert len(Seq(genome[(pep_pos):pep_pos+3]).reverse_complement()) % 3 == 0
            amino = translate(Seq(genome[(pep_pos):pep_pos+3]).reverse_complement(), cds = False, table = 11)
            assert len(genome[pep_pos:pep_pos + 3]) == 3 
        elif strand == '+':
            pep_pos = start + position
            upstream_pos = pep_pos - 3
            amino = translate(Seq(genome[(upstream_pos -1):pep_pos-1]), cds = False, table =11)
            assert len(genome[(upstream_pos -1):pep_pos-1]) == 3
        if amino in cleavage:
            cleavage_pep = True         
    return cleavage_pep

def get_start_coords(seq, coord, genome, starts, stops): # trailing end of a frame (from first found peptide), coordinates of frame. Returns the coordinates with the most downstream start codon for that sequence
    strand = coord.split(')')[0][1:]
    start = int(coord.split(')')[1].split(':')[0])-1
    end = int(coord.split('(')[1].split(':')[1])
    if strand == '+':
        assert len(genome[start:end]) % 3 == 0
        original_seq = translate(Seq(str(genome)[start:end]), table = 11, cds = False)
        position = (original_seq.find(seq[1:])-1) * 3 
        seq_pos = start + position
        #print genome[seq_pos -3: seq_pos + 3], genome[seq_pos:seq_pos + 3], translate(Seq(genome[seq_pos:seq_pos + 9])), seq[:10]
        if str(Seq(genome[seq_pos:seq_pos + 3])) not in starts:
            while (str(genome)[seq_pos - 3:seq_pos] not in starts + stops) and (seq_pos >= 0):
                seq_pos -= 3
                #print genome[seq_pos:seq_pos + 3],
            final_codon = str(Seq(genome[seq_pos -3: seq_pos]))
            #print final_codon
            assert final_codon in starts
            start = seq_pos - 3
        else:
            start = seq_pos
            assert genome[start: start + 3] in starts
    elif strand == '-':
        test_str = str(Seq(genome[end-6:end]).reverse_complement())
        original_seq = translate(Seq(str(genome)[start:end]).reverse_complement(), table = 11, cds = False)
        
        assert len(Seq(str(genome)[start:end]).reverse_complement()) % 3 == 0
        position = (original_seq.find(seq[1:]) -1) *3
        seq_pos = end - position 
        temp_codon = Seq(genome[seq_pos -17:seq_pos]).reverse_complement()
        if str(Seq(genome[seq_pos -3:seq_pos]).reverse_complement()) not in starts:
            while (str(Seq(genome[seq_pos:seq_pos +3]).reverse_complement()) not in starts + stops) and (seq_pos < len(genome)):
                seq_pos += 3
            final_codon= str(Seq(genome[seq_pos:seq_pos + 3]).reverse_complement())
            assert final_codon in starts
            end = seq_pos + 3
        else:
            end = seq_pos
            assert str(Seq(genome[seq_pos - 3 : seq_pos]).reverse_complement()) in starts
    return '({}){}:{}'.format(strand, start + 1, end)

def get_nucs(coord, genome):
    strand = coord.split(')')[0][1:]
    end = int(coord.split(':')[1])
    start = int(coord.split(')')[1].split(':')[0])
    if strand == '+':
        seq = genome[start-1:end]
    elif strand =='-':
        seq = str(Seq(genome[start-1:end]).reverse_complement())
    return seq


def ps(peptides, protein, frame1, frame2, frame3, frame4, frame5, frame6):
    gssps = []
    pssps = []
   
    protein = protein.upper()

    lp = len(protein)
    lp_replace = 'X' * lp

    #print 'lp_replace:', lp_replace
    for m in peptides:
        temp = m
        if protein.find(m) == 0:
            m = m[1:]
        minilocs = 0
        
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame1)]    
        minilocs += len(locations)
        
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame2)]
        minilocs += len(locations)
        
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame3)]
        minilocs += len(locations)
       
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame4)]
        minilocs += len(locations)
        
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame5)]
        minilocs += len(locations)
        
        locations = [k.start() for k in re.finditer('(?={})'.format(m), frame6)]
        minilocs += len(locations)
        
        if minilocs == 1:
            gssps.append(temp)

        if minilocs >= 1:
            minilocs = 0
            
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame1.replace(protein[1:], lp_replace[1:]))]    
            minilocs += len(locations)
            
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame2.replace(protein[1:], lp_replace[1:]))]
            minilocs += len(locations)
            
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame3.replace(protein[1:], lp_replace[1:]))]
            minilocs += len(locations)
           
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame4.replace(protein[1:], lp_replace[1:]))]
            minilocs += len(locations)
            
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame5.replace(protein[1:], lp_replace[1:]))]
            minilocs += len(locations)
            
            locations = [k.start() for k in re.finditer('(?={})'.format(m), frame6.replace(protein[1:], lp_replace[1:]))]
            minilocs += len(locations)
            
            if minilocs == 0:
                pssps.append(temp)
    return gssps, pssps


def novel_columns(df, genome,cdna):
    features = defaultdict(list)
    #frame1 = str(translate(Seq(genome[:]), cds =False, table = 11))
    #frame2 = str(translate(Seq(genome[1:]), cds = False, table = 11))
    #frame3 = str(translate(Seq(genome[2:]), cds = False, table = 11))
    #frame4 = str(translate(Seq(genome[:]).reverse_complement(), cds = False, table = 11))
    #frame5 = str(translate(Seq(genome[:-1]).reverse_complement(), cds = False, table = 11))
    #frame6 = str(translate(Seq(genome[:-2]).reverse_complement(), cds = False, table = 11))

    for row in df.iterrows():
        evidence = []
        evidence_code = 0
        nblasted = []
        datum = row[1]
        count = row[0]
        print count
        if datum['Alternate Start Translations'] == 'True':
            alt = True
        else:
            alt = False
        new_coords = datum['Consensus Coordinates'].split('\n')
        nucs = None
        overlapped = []
        pseudogene = 'False'
        sense_overlapped = []
        for coord in new_coords:
            nucs = get_nucs(coord, genome)
            ndatum = blast.nblast_pretty(nucs, 'MsmegmatisCDNAdb')
            start = int(coord.split(')')[1].split(':')[0])
            end = int(coord.split(':')[1])
            strand = coord.split(')')[0].split('(')[1]
            if strand == '+':
                strand = '1'
            elif strand == '-':
                strand = '-1'
            for f in cdna:
                nstart = int(f.description.split(':Chromosome:')[1].split(':')[0])
                nend = int(f.description.split(':Chromosome:')[1].split(':')[1])
                nstrand = f.description.split(':Chromosome:')[1].split(':')[2].split()[0]
                if ((start >= nstart ) and (start < nend)) or ((end <= nend) and (end > nstart)):
                    overlap = '{} overlaps with: {}'.format(coord, f.description)
                    overlapped.append(overlap)
                    if strand == nstrand:
                        sense_overlapped.append(overlap)
                    if 'pseudogene' in f.description.lower():
                        pseudogene = 'True'
            if len(ndatum) > 0:
                for rec in ndatum:
                    rstrand = rec.split(':Chromosome:')[1].split(':')[2].split()[0]
                    if strand == rstrand:
                        _ = coord+ ' ' + rec
                        nblasted.append(_)
        if len(nblasted) > 0:
            df.loc[count, 'CDNA blastn'] = '\n'.join(nblasted)
            evidence.append('Genomic sense CDNA feature allignment')
        else:
            df.loc[count, 'CDNA blastn'] = np.nan
        assert datum['Annotation_Type'] == 'Novel'
        if len(overlapped) == 0:
            df.loc[count, 'CDNA Overlaps'] = 'None'
        else:
            df.loc[count, 'CDNA Overlaps'] = '\n'.join(overlapped)
        if len(sense_overlapped) == 0:
            df.loc[count, 'CDNA Overlaps (Sense)'] = 'None'
        else:
            df.loc[count, 'CDNA Overlaps (Sense)'] = '\n'.join(sense_overlapped)
            evidence.append('Genomic sense CDNA feature overlap')
        df.loc[count, 'Pseudogene Overlap'] = pseudogene
        df.loc[count, 'nr blastp'] = '_'
        seq = StringIO.StringIO('>' + datum['Consensus Sequence'].split('>')[1])
        seq = SeqIO.read(seq,'fasta')
        longest_seq_str = str(seq.seq).upper() 
        
        #peptides = [''.join(''.join(''.join(p.split('_')).split('(ac)')).split('(ox)')) for p in datum['Non-Redundant Peptide Set'].split('\n')]
        #gss, pss = ps(peptides, longest_seq_str, frame1, frame2, frame3, frame4, frame5, frame6)
        
        gss  = df.loc[count, 'Genome Search Specific Peptides']
        pss  = df.loc[count, 'Protein Search Specific Peptides']
        
        if gss == np.nan:
            gss = ''
        if pss == np.nan:
            pss = ''

        if gss != '':
            gss = gss.split('\n')
        if pss != '':
            pss = pss.split('\n')

        print 'GSS', gss
        print 'PSS', pss
        
        num_peps = 'None'
        if len(pss) >= 2:
            num_peps = 'Two or more identified peptides'
            evidence.append(num_peps)
        
        if len(pss) == 1:
            num_peps = 'Only one identified peptide'
            evidence.append(num_peps)

        if len(gss) > 0:
           df.loc[count, 'GSSPs'] = '\n'.join([str(val) for val in gss])
        if len(pss) > 0:
            df.loc[count, 'PSSPs'] = '\n'.join([str(val) for val in pss])
       
        gssm_confirmed = False
        if ((len(gss) > 0) or (len(pss) > 0)):
            df.loc[count, 'GSSM or PSSM Peptides'] = 'True'
            gssm_confirmed = True
        else:
            df.loc[count, 'GSSM or PSSM Peptides'] = 'False'
        
        if gssm_confirmed == True:
            if alt == True:
                res = blast.pblast_pretty(longest_seq_str[1:],'nr')
                df.loc[count, 'nr blastp'] = res
            else:
                res = blast.pblast_pretty(longest_seq_str,'nr')
                df.loc[count, 'nr blastp'] =  res
            #df.loc[count, 'TeST'] = longest_seq_str
            if res != None:
                evidence.append('nr blastp allignment')
                res_accession = res.split('gi|')[1].split('|')[0]
                res_rec = blast.gi2up(res_accession)
                df.loc[count, 'Leading blastp GI id'] = res_accession
                if res_rec != None:
                    for r in res_rec:
                        if not isinstance(res_rec[r], basestring):
                            df.loc[count,r] = '\n'.join(res_rec[r])
                            for feature in res_rec[r]:
                                features[r].append(feature)
                        else:
                            df.loc[count, r] = res_rec[r]
                            features[r].append(res_rec[r])
        else:
            df.loc[count, 'nr blastp'] ='Sequence excluded (failed GSSP/PSSP search)'
        
        if ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and ('Genomic sense CDNA feature overlap' in evidence) and (num_peps == 'Two or more identified peptides'):
            evidence_code = 1
        
        elif ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and ('Genomic sense CDNA feature allignment' in evidence) and (num_peps == 'Two or more identified peptides'):
            evidence_code = 2

        elif ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and (num_peps == 'Two or more identified peptides'):
            evidence_code = 3

        elif (gssm_confirmed == True) and (num_peps == 'Two or more identified peptides') and ('Genomic sense CDNA feature overlap' in evidence): 
            evidence_code = 4
        
        elif (gssm_confirmed == True) and (num_peps == 'Two or more identified peptides') and ('Genomic sense CDNA feature allignment' in evidence): 
            evidence_code = 5
        
        elif (gssm_confirmed == True) and (num_peps == 'Two or more identified peptides'): 
            evidence_code = 6

        elif ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and ('Genomic sense CDNA feature overlap' in evidence) and (num_peps == 'Only one identified peptide'):
            evidence_code = 7
        
        elif ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and ('Genomic sense CDNA feature allignment' in evidence) and (num_peps =='Only one identified peptide'):
            evidence_code = 8

        elif ('nr blastp allignment' in evidence) and (gssm_confirmed == True) and (num_peps == 'Only one identified peptide'):
            evidence_code = 9
        
        elif (gssm_confirmed == True) and ('Genomic sense CDNA feature overlap' in evidence) and (num_peps == 'Only one identified peptide'):
            evidence_code = 10
        
        elif (gssm_confirmed == True) and ('Genomic sense CDNA feature allignment' in evidence) and (num_peps == 'Only one identified peptide'):
            evidence_code = 11

        elif (gssm_confirmed == True) and (num_peps == 'Only one identified peptide'):
            evidence_code = 12

        elif num_peps == 'None':
            evidence_code = 13
        else:
            print evidence
            assert 4 == 5
        df.loc[count, 'Evidence'] = '\n'.join(evidence)
        df.loc[count, 'Evidence Code (Ranked)'] = evidence_code

    df.sort('Evidence Code (Ranked)', ascending = True, inplace = True)
    return df, features

def PGCombined(mapping_dct, ordered, stage_dct):
    stage1 = stage_dct.keys()[0]
    stage2 = stage_dct.keys()[1]
    stage1_values = stage_dct[stage1]
    stage2_values = stage_dct[stage2]
    txt_dct=defaultdict()
    fasta_dict= {}
    fasta_records = {}
    all_peps = {}
    
    unique_peps = {}
    names= name_dct()
    sum_list = []
    pg_dct = defaultdict()
    pg_mult_dct = defaultdict()
    id_dct = defaultdict(list) 
    ev_dct = {}
    for i in mapping_dct:
        if i == 'mapping':
            f= open(mapping_dct['mapping'])
            mapping = json.load(f)
        elif i == 'flatfile':
            f = mapping_dct['flatfile']
            genome = SeqIO.read(f, 'embl')
            genome = str(genome.seq)
        else:
            tup = mapping_dct[i]
            fasta_path=tup[0]
            seq_dct, rec_dct = fasta_dct(fasta_path)
            fasta_dict[i] = seq_dct
            fasta_records[i] = rec_dct
            txt_path =tup[1]
            pg, pg_mult, sum  = filteredPG(txt_path, i)
            evidence = evidence_table(txt_path, i)
            ev_dct[i] = evidence 
            sum_list.append(sum)
            pg_dct[i] = pg
            pg_mult_dct[i] = pg_mult
            peps, unique = peptides(txt_path)
            all_peps[i]=peps
            unique_peps[i]=unique
    
    frame1 = str(translate(Seq(genome[:]), cds =False, table = 11))
    frame2 = str(translate(Seq(genome[1:]), cds = False, table = 11))
    frame3 = str(translate(Seq(genome[2:]), cds = False, table = 11))
    frame4 = str(translate(Seq(genome[:]).reverse_complement(), cds = False, table = 11))
    frame5 = str(translate(Seq(genome[:-1]).reverse_complement(), cds = False, table = 11))
    frame6 = str(translate(Seq(genome[:-2]).reverse_complement(), cds = False, table = 11))

    pg_summary = pd.concat(sum_list, axis = 1)
    pg_summary.rename(columns=names, inplace =True)
    venn_dct = defaultdict(list)
    for i in pg_dct:
        id_dct[i] = pg_dct[i]['Protein IDs'].tolist()
    combined = DataFrame()
    count = 0
    new_cols = []
    for i in ordered:
        query_name = '_'.join(i.split())
        id_name = 'Leading_Protein_ID\n{}'.format(query_name)
        new_cols.append(id_name)
        unique_peptides = 'Unique_Peptides\n{}'.format(query_name)
        new_cols.append(unique_peptides)
        non_unique_peptides = 'Non_Unique_Peptides\n{}'.format(query_name)
        new_cols.append(non_unique_peptides)
        pep_scores = 'PEP\n{}'.format(query_name)
        new_cols.append(pep_scores)
        group_count = 'Group_Members\n{}'.format(query_name)
        new_cols.append(group_count)

        #start_identified = 'Start_Identified_{}'.format(query_name)
        #new_cols.append(start_identified) 

    new_cols.append('First_Amino_Found')
    new_cols.append('Most_Upstream_ID(s)')
    new_cols.append('Reference IDs Mapped')
    new_cols.append('Consensus Sequence')
    new_cols.append('Consensus Coordinates')
    new_cols.append('Start Codon') 
    new_cols.append('Start Translation') 
    new_cols.append('Identified Start Peptide At Trypsin Cleavage Site')
    new_cols.append('Annotation_Type')
    new_cols.append('Cleavage Site Peptides')
    new_cols.append('Cleavage Isoforms')
    new_cols.append('Acetyl (Protein N-term) Peptides')
    new_cols.append('Oxidation (M) Peptides')
    new_cols.append('Stage Unique: {}'.format(stage1))
    new_cols.append('Stage Unique: {}'.format(stage2))
    new_cols.append('Non-Redundant Peptide Set')
    new_cols.append('Alternate Start Translations')
    new_cols.append('Genome Search Specific Peptides')
    new_cols.append('Protein Search Specific Peptides')
    
    #new_cols.append('Leading blastp gi id')
    #new_cols.append('Annotations')
    #new_cols.append('CDS_Coordinates')
    #new_cols.append('Mulitple Start Sites')
    #new_cols.append('N-term acetylation Peptides (Combined)')
    #new_cols.append('Peptide_IDs_Combined')
    #new_cols.append('Consensus Sequence')
    #new_cols.append('Translation Variants')

    for i in ordered[:]:
        query_ids = id_dct[i]
        df = pg_dct[i]
        ev = ev_dct[i]
        fs = fasta_dict[i]
        fr =fasta_records[i]
        query_name ='_'.join(i.split())
        ordered.remove(i)
        id_name = 'Leading_Protein_ID\n{}'.format(query_name)
        id_col1= 'Unique_Peptides\n{}'.format(query_name)
        id_col2= 'Non_Unique_Peptides\n{}'.format(query_name)
        id_col3='PEP\n{}'.format(query_name)
        id_col4 = 'Group_Members\n{}'.format(query_name)
        for id in query_ids:
            gssps = []
            pssps = []
            non_redundant_peptides = []
            stage1_peptides = []
            stage2_peptides = []
            acetylations = []
            oxidations = []
            covered = []
            covered.append(i)
            new_id = id.split(';')[0]
            ref_seq_present = False
            if i == 'ref_prot':
                ref_seq_present = True
            reference_prot = None
            row_recs = {}
            combined_map = set()
            start_peptides = []
            len_dict = defaultdict(list)    # dict of the most upstream pep found  position per seq 
            starts_found = []
            row = df[df['Protein IDs'] == id]
            assert len(row) == 1
            peptide_ids=row['Peptide IDs'].iget(0).split(';')
            evidence_ids = row['Evidence IDs'].iget(0).split(';')
            evidence_peps = ev[ev['id'].apply(str).isin(evidence_ids)]
            
            combined_peps = []
            
            for pep in list(set(evidence_peps['Modified sequence'])):
                non_redundant_peptides.append(pep)
                if '(ac)' in pep:
                    acetylations.append(pep)
                if '(ox)' in pep:
                    oxidations.append(pep)
                datum = ''.join(pep.split('(ac)'))
                datum = ''.join(datum.split('(ox)'))
                datum = ''.join(datum.split('_'))
                combined_peps.append(datum)

            combined_peps = list(set(combined_peps))
            for pep in list(set(evidence_peps[evidence_peps['Experiment'].isin(stage1_values)]['Modified sequence'])):
                stage1_peptides.append(pep)
            for pep in list(set(evidence_peps[evidence_peps['Experiment'].isin(stage2_values)]['Modified sequence'])):
                stage2_peptides.append(pep)
           
            pep_score = row['PEP'].iget(0)
            group_members = row['Number of proteins'].iget(0)
            unique_peptides = [unique_peps[query_name][int(pep_id)] for pep_id in peptide_ids if int(pep_id) in unique_peps[query_name]]
            non_unique_peps = [all_peps[query_name][int(pep_id)] for pep_id in peptide_ids if int(pep_id) in all_peps[query_name]]
            
            row_peps = combined_peps
            
            if len(combined_peps) > 0:
                pep_trie = algo.trie_graph(combined_peps)
            temp_id = fr[new_id].id
            temp_description = fr[new_id].description
            row_recs[i] = fr[new_id]
            temp_seq = str(fr[new_id].seq)     #the protein sequence
            first_row_seq = temp_seq
            if i == 'ref_prot':
                reference_prot = fr[new_id]

            confirmed_unique = []
            if len(combined_peps) > 0:    
                gss, pss = ps(row_peps, temp_seq, frame1, frame2, frame3, frame4, frame5, frame6) 
                confirmed_unique = pss
                c_u_trie  = algo.trie_graph(confirmed_unique)
                positions = algo.trie_matching(c_u_trie, temp_seq)
                for p in gss:
                    if p not in gssps:
                        gssps.append(p)
                for p in pss:
                    if p not in pssps:
                        pssps.append(p)
            
            else:
                positions = []
            if positions[:1] == 0:
                starts_found.append(query_name)
            verify = temp_seq.lower()

            if len(combined_peps) > 0:
                temp_seq = algo.trie_upper(pep_trie, temp_seq)
            else:
                temp_seq = temp_seq.lower()

            temp_seq_upper = temp_seq.upper()
            #check if peptide starts at a not cleavage site
            for peptide in confirmed_unique:
                if cleavage_site(peptide, fr[new_id], genome) == False:
                    start_peptides.append(peptide)
            
            assert verify == temp_seq.lower()

            if len(positions) > 0:
                upstream = positions[0]
                temp_upstream = verify[upstream:]
            else:
                temp_upstream = ''
            len_upstream = len(temp_upstream)
            len_dict[len_upstream].append(i)
            temp_rec = SeqRecord(seq = Seq(temp_seq), id= temp_id, description = temp_description)
            combined.loc[count, id_name]=temp_rec.format('fasta')
            combined.loc[count,id_col2 ]='\n'.join(non_unique_peps)
            combined.loc[count, id_col1] = '\n'.join(unique_peptides)
            combined.loc[count, id_col3] = pep_score
            combined.loc[count, id_col4] = group_members
            venn_dct[i].append(abs(int(count)))
            found = False
            seq = fs[new_id]
            try:
                map = mapping[seq]
            except:
                try:
                    map = mapping['V' + seq[1:]]
                except:
                    try:
                        map = mapping['L'+seq[1:]]
                    except:
                        map = [10110000000]
            combined_map.update(map)
            for j in ordered[:]:
                found=False
                temp_name = '_'.join(j.split())
                template_ids = id_dct[j]     
                ev1 = ev_dct[j]
                tdf = pg_dct[j]
                tfs = fasta_dict[j]
                for k in template_ids:
                    new_k = k.split(';')[0]
                    temp_seq = tfs[new_k]
                    if found == False:
                        try:
                            temp_map = mapping[temp_seq]
                        except:
                            try: 
                                temp_map = mapping['L'+ temp_seq[1:]]
                            except:
                                try:
                                    temp_map = mapping['V'+temp_seq[1:]]
                                except:
                                    temp_map = [1000000000]
                        intersection = set(map).intersection(temp_map)
                        if len(intersection) >= 1:
                            if j == 'ref_prot':
                                ref_seq_present = True
                                reference_prot = fasta_records[j][new_k]
                            covered.append(j)
                            combined_map.update(temp_map)
                            #combined.loc[count, 'Leading_Protein_ID_{}'.format(temp_name)]=fasta_records[j][k].format('fasta')
                            query_id_name = 'Leading_Protein_ID\n{}'.format(temp_name)
                            query_col1= 'Unique_Peptides\n{}'.format(temp_name)
                            query_col2= 'Non_Unique_Peptides\n{}'.format(temp_name)
                            query_col3 = 'PEP\n{}'.format(temp_name)
                            query_col4 = 'Group_Members\n{}'.format(temp_name)
                            row = tdf[tdf['Protein IDs'] == k]
                            assert len(row) == 1
                            query_peptide_ids=row['Peptide IDs'].iget(0).split(';') 
                            evidence_ids = row['Evidence IDs'].iget(0).split(';')
                            evidence_peps = ev1[ev1['id'].apply(str).isin(evidence_ids)]
                            
                            combined_peps = []

                            for pep in list(set(evidence_peps['Modified sequence'])):
                                non_redundant_peptides.append(pep)
                                if '(ac)' in pep:
                                    acetylations.append(pep)
                                if '(ox)' in pep:
                                    oxidations.append(pep)
                                datum = ''.join(pep.split('(ac)'))
                                datum = ''.join(datum.split('(ox)'))
                                datum = ''.join(datum.split('_'))
                                combined_peps.append(datum)

                            combined_peps = list(set(combined_peps))

                            for pep in list(set(evidence_peps[evidence_peps['Experiment'].isin(stage1_values)]['Modified sequence'])):
                                stage1_peptides.append(pep)
                            for pep in list(set(evidence_peps[evidence_peps['Experiment'].isin(stage2_values)]['Modified sequence'])):
                                stage2_peptides.append(pep)

                            pep_score = row['PEP'].iget(0)
                            group_members = row['Number of proteins'].iget(0)
                            unique_peptides = [unique_peps[temp_name][int(pep_id)] for pep_id in query_peptide_ids if int(pep_id) in unique_peps[temp_name]]
                            non_unique_peps = [all_peps[temp_name][int(pep_id)] for pep_id in query_peptide_ids if int(pep_id) in all_peps[temp_name]] 
                            
                            
                            #combined_peps = list(set(unique_peptides+non_unique_peps))
                            
                            for pep in combined_peps:
                                row_peps.append(pep)
                            
                            if len(combined_peps) > 0:
                                pep_trie = algo.trie_graph(combined_peps)
                            
                            temp_id = fasta_records[j][new_k].id
                            temp_description = fasta_records[j][new_k].description
                            row_recs[j] = fasta_records[j][new_k]
                            temp_seq = str(fasta_records[j][new_k].seq) 
                            confirmed_unique = []

                            if len(combined_peps) > 0:
                                gss, pss = ps(combined_peps, temp_seq, frame1, frame2, frame3, frame4, frame5, frame6) 
                                confirmed_unique = pss
                                c_u_trie  = algo.trie_graph(confirmed_unique)
                                positions = algo.trie_matching(c_u_trie, temp_seq)
                                for p in gss:
                                    if p not in gssps:
                                        gssps.append(p)
                                for p in pss:
                                    if p not in pssps:
                                        pssps.append(p)
                            else:
                                positions = []

                            if positions[:1] == 0:
                                starts_found.append(temp_name)
                            
                            for peptide in confirmed_unique:
                                if cleavage_site(peptide, fasta_records[j][new_k], genome) == False:
                                    start_peptides.append(peptide)
                            
                            if len(positions) > 0:
                                upstream = positions[0]
                                temp_upstream = temp_seq[upstream:]
                            else:
                                temp_upstream = ''
                            len_upstream = len(temp_upstream)

                            len_dict[len_upstream].append(j)
                            
                            if len(combined_peps) > 0:
                                temp_seq = algo.trie_upper(pep_trie, temp_seq)
                            else:
                                temp_seq = temp_seq.lower()

                            temp_rec = SeqRecord(seq = Seq(temp_seq),
                                    description = temp_description,
                                    id = temp_id)
                            combined.loc[count, query_id_name]=temp_rec.format('fasta')
                            combined.loc[count,query_col2 ]='\n'.join(non_unique_peps)
                            combined.loc[count, query_col1] = '\n'.join(unique_peptides)
                            combined.loc[count, query_col3] = pep_score
                            combined.loc[count, query_col4] = group_members
                            venn_dct[j].append(count)
                            id_dct[j].remove(k)
                            found=True

            non_redundant_peptides = list(set(non_redundant_peptides))
            stage1_peptides_new = list(set([pep for pep in stage1_peptides if pep not in stage2_peptides]))
            stage2_peptides_new = list(set([pep for pep in stage2_peptides if pep not in stage1_peptides]))
            acetylations = set(acetylations)
            oxidations = set(oxidations)
            
            combined.loc[count, 'Acetyl (Protein N-term) Peptides'] = '\n'.join(acetylations)
            combined.loc[count, 'Oxidation (M) Peptides'] = '\n'.join(oxidations)
            combined.loc[count, 'Stage Unique: {}'.format(stage1)] = '\n'.join(stage1_peptides_new)
            combined.loc[count, 'Stage Unique: {}'.format(stage2)] = '\n'.join(stage2_peptides_new)
            combined.loc[count, 'Non-Redundant Peptide Set'] = '\n'.join(non_redundant_peptides)
            if len(pssps) > 0:
                combined.loc[count, 'Genome Search Specific Peptides'] = '\n'.join(gssps)
                combined.loc[count, 'Protein Search Specific Peptides'] = '\n'.join(pssps)
            
            covered = ''.join(list(set(covered)))   #checks that the only hit was from a single database

            combined.loc[count,'First_Amino_Found'] = '\n'.join(starts_found)       
            most_upstream = max(len_dict)
            longest_seqs = []
            for item in len_dict[most_upstream]:
                temp = row_recs[item]
                seq = str(temp.seq)[-most_upstream:]
                if seq not in longest_seqs:
                    longest_seqs.append(seq)
            combined.loc[count, 'Alternate Start Translations'] = str(len(longest_seqs) > 1)
            combined.loc[count, 'Most_Upstream_ID(s)'] = '\n'.join(len_dict[most_upstream])
            refs_mapped = []
            for reference_record in fasta_records['ref_prot']:
                rec_seq = str(fasta_records['ref_prot'][reference_record].seq)
                try:
                    intersection = combined_map.intersection(mapping[rec_seq])  
                    if len(intersection) >= 1:
                        refs_mapped.append(fasta_records['ref_prot'][reference_record])
                except:
                    pass
             
            combined_trie = algo.trie_graph(row_peps)
            refs_mapped_upper = [SeqRecord(seq = Seq(algo.trie_upper(combined_trie, str(ref_rec.seq))), id = ref_rec.id, description = ref_rec.description).format('fasta') for ref_rec in refs_mapped]
            #combined.loc[count, 'Reference IDs Mapped'] = '\n'.join([ref_rec.format('fasta') for ref_rec in refs_mapped])
            combined.loc[count, 'Reference IDs Mapped'] = '\n'.join(refs_mapped_upper)

            reference_sequence =list(set([str(ref_rec.seq) for ref_rec in refs_mapped]))
            novel = False        
            
            if (len(reference_sequence) < 1):
                if (len(refs_mapped) == 0) and (ref_seq_present != True):
                    novel = True
                    combined.loc[count, 'Annotation_Type'] = 'Novel'
                elif (len(refs_mapped) == 0) and (covered == 'ref_prot') and (most_upstream == len(first_row_seq)):
                    combined.loc[count, 'Annotation_Type'] = 'Validation'
            
            elif (len(reference_sequence) == 1):
                if most_upstream == len(reference_sequence[0]):
                    combined.loc[count, 'Annotation_Type'] = 'Validation'
                elif most_upstream > len(reference_sequence[0]):
                    combined.loc[count, 'Annotation_Type'] = 'Upstream Start'
            
            elif len(reference_sequence) > 1:
                ref_lens = []
                annotations = []
                longest_reference = 0
                for ref in refs_mapped:
                    ref_lens.append(len(str(ref.seq)))
                    datum = len(str(ref.seq))
                    if datum > longest_reference:
                        longest_reference = datum
                if most_upstream > longest_reference:
                    combined.loc[count, 'Annotation_Type'] = 'Upstream Start'
                elif most_upstream in ref_lens:
                    combined.loc[count, 'Annotation_Type'] = 'Validation'
            
            combined.loc[count, 'Cleavage Site Peptides'] = '\n'.join(list(set(start_peptides)))
            
            longest_seq_str = str(row_recs[len_dict[most_upstream][0]].seq)[-most_upstream:]
            
            cleavage_peps_found = False

            if len(start_peptides) > 0:
                cleavage_peps_found = True
                cleavage_trie = algo.trie_graph(start_peptides)
                clv_lst = algo.trie_matching(cleavage_trie, longest_seq_str) 
                combined.loc[count, 'Cleavage Isoforms'] = len(clv_lst)
            else:
                combined.loc[count, 'Cleavage Isoforms'] = 0
            rec_key = [key for key in row_recs.keys() if ((key != 'ref_prot') and (len(str(row_recs[key].seq)) >= most_upstream) and (longest_seq_str in str(row_recs[key].seq)))]
            
            if len(rec_key) != 0:
                longest_seq_coords =row_recs[rec_key[0]].description.split()
                coords = []
                for item in longest_seq_coords:
                    if (item.startswith('(+)') or item.startswith('(-)')):
                        coords.append(item)
            else:
                coords = []
                rec_key = [key for key in row_recs.keys() if ((key == 'ref_prot') and (len(str(row_recs[key].seq)) >= most_upstream) and (longest_seq_str in str(row_recs[key].seq)))]

                if len(rec_key) != 0:
                    longest_seq_coords =row_recs[rec_key[0]].description.split()
                    coords = []
                    for item in longest_seq_coords:
                        if (item.startswith('(+)') or item.startswith('(-)')):
                            coords.append(item)

            if len(coords) == 1:
                nblasted = [] 
                new_coords = []
                starts = ['ATG', 'GTG', 'TTG']
                stops =  ['TGA', 'TAA', 'TAG']
                coords = coords[0].split('|')
                for coord in coords:
                    new_coord = get_start_coords(longest_seq_str, coord, genome, starts, stops)
                    new_coords.append(new_coord)
                combined.loc[count, 'Consensus Coordinates']  = '\n'.join(new_coords) 
                start_codons = []
                for coord in new_coords:
                    nucs = get_nucs(coord, genome) 
                    start_codon = nucs[:3]
                    start_codons.append(start_codon)
                    #if novel == True:
                    #    combined.loc[count, 'nr blastp'] = '_'
                    #    if len(longest_seqs) > 1:
                    #        res = blast.pblast_pretty(longest_seq_str.upper()[1:],'nr')
                    #        combined.loc[count, 'nr blastp'] = res
                    #    else:
                    #        res = blast.pblast_pretty(longest_seq_str.upper(),'nr')
                    #        combined.loc[count, 'nr blastp'] =  res
                    #    
                    #    if res != None:
                    #        res_accession = res.split('gi|')[1].split('|')[0]
                    #        res_rec = blast.gi2up(res_accession)
                    #        if res_rec != None:
                    #            for r in res_rec:
                    #                combined.loc[count, 'Leading blastp gi id'] = res_accession
                    #                combined.loc[count,r] = '\n'.join(res_rec[r])
                    #    
                    #    datum = blast.nblast_pretty(nucs, 'MsmegmatisCDNAdb')
                    #    if len(datum) > 0:
                    #        for rec in datum:
                    #            _ = coord+ ' ' + rec
                    #            nblasted.append(_)
                #if len(nblasted) > 0:
                    #combined.loc[count, 'CDNA blastn'] = '\n'.join(nblasted)
                assert len(nucs) % 3 == 0
                consensus = translate(Seq(nucs), cds = False, table = 11)
                if consensus.endswith('*'):
                    consensus = consensus[:-1]
                if len(consensus) == len(longest_seq_str):
                    consensuses = []
                    start_amini = []
                    mini_count = 1
                    for seq in longest_seqs:
                        start_amino  = seq[:1] 
                        consensus = algo.trie_upper(combined_trie, seq)
                        consensus_rec = SeqRecord(seq = Seq(consensus), id = 'Consensus_Protein_Sequence_{}.{}'.format(count, mini_count) , description = '|'.join(new_coords))
                        consensuses.append(consensus_rec.format('fasta'))
                        start_amini.append(start_amino)
                        mini_count  += 1
                    start_amini.sort()
                    combined.loc[count, 'Consensus Sequence'] = '\n'.join(consensuses)
                    start_amini.sort()
                    combined.loc[count, 'Start Translation'] = ', '.join(start_amini)
                    if cleavage_peps_found == True:
                        if clv_lst[0] == 0:
                            combined.loc[count,  'Identified Start Peptide At Trypsin Cleavage Site'] = 'False'
                        else:
                            combined.loc[count, 'Identified Start Peptide At Trypsin Cleavage Site'] = 'True'
                    else:
                        combined.loc[count, 'Identified Start Peptide At Trypsin Cleavage Site'] = 'True'

                else:
                    consensus = algo.trie_upper(combined_trie, consensus)
                    consensus_rec = SeqRecord(seq = Seq(consensus), id = 'Consensus_Protein_Sequence_{}'.format(count) , description = '|'.join(new_coords))
                    combined.loc[count, 'Consensus Sequence'] = consensus_rec.format('fasta')
                    combined.loc[count, 'Start Translation'] = 'Not Verified'
                start_codons = list(set(start_codons))
                start_codons.sort()
                combined.loc[count, 'Start Codon'] = ', '.join(start_codons)
            print count
            count += 1
            

    mult_df = []
    for i in pg_mult_dct:
        datum = pg_mult_dct[i]
        datum['Database'] = i
        new = ['Database']
        if len(datum) > 0:
            datum = add_fasta(datum, fasta_records, all_peps, unique_peps, i)
            old = filter(lambda a: a != 'Database', datum.columns)
            new += old
            datum = datum[new]
            mult_df.append(datum)
    mult_df = pd.concat(mult_df, axis = 0)
    mult_df = mult_df[new]
    combined = combined[combined['Protein Search Specific Peptides'].notnull()]
    combined.reset_index(inplace=True)
    del combined['index']
    return pg_summary, combined[new_cols], venn_dct, mult_df,genome 

def venn(dct, row, col, worksheet, names):
    temp_dir = tempfile.mkdtemp()
    temp_out = temp_dir+'/out.png'
    sets = []
    new_names = []
    n = name_dct()
    for i in names:
        temp = set(dct[i])
        sets.append(temp)
    names = tuple(names)
    if len(names) == 3:
        v = venn3([i for i in sets], names, alpha=0.4, normalize_to=1.0)
    elif len(names) == 2:
        v = venn2([i for i in sets], names,  alpha=0.4, normalize_to=1.0)
    plt.savefig(temp_out, bbox_inches='tight')
    plt.clf()
    worksheet.insert_image(row, col, temp_out)
