#!/usr/bin/env Rscript 

library("dplyr")
library("optparse")
library("MSnbase")

options(bitmapType='cairo')

option_list = list(
 make_option(c("-m", "--mgf"), type="character", default=NULL, 
              help="Directory of mzIdentML files for global FDR control", metavar="character"),
 make_option(c("-v", "--psms"), type="character", default=1, 
              help="Percentage value to control the FDR", metavar="character"),
 make_option(c("-l","--fdr_level"), type="character", default='accession',
              help="The level to control the FDR ('PSM', 'peptide' or 'accession')", metavar="character"))

opt_parser = OptionParser(option_list=option_list);
opt = parse_args(opt_parser);

mgf = opt$mgf   # convert percentage to ratio
identfile <- opt$psms
msexp <- readMgfData(mgf)
msexp <- addIdentificationData(msexp, id = identfile, verbose = TRUE )
quit()


if (is.null(opt$indir)){
  print_help(opt_parser)
  stop("At least one argument must be supplied (input directory).n", call.=FALSE)
} 

unlink(paste(opt$indir,"/analysis",sep=''), recursive=TRUE)

dirfiles <- list.files(opt$indir, full.names=TRUE, pattern='.mzid')


if (is.null(opt$outdir)) {
	outdir <- paste(opt$indir,'/analysis',sep='');
} else { outidr <- opt$outdir} 

dir.create(outdir,showWarnings=TRUE,recursive=FALSE,mode='0777')


sink(paste(outdir, '/log.txt',sep=''))

print(dirfiles)
library("MSnID")
.strip_flanking_AAs <- function(peptide)
{
    # INPUT: Peptide sequence with flanking AAs e.g. "K.APEP*TID{34.34}E%.-"
    # OUPUT: Peptide without flanking "APEP*TID{34.34}E%"
    #
    # this is quicker, but may not be safe if there are some mods with dots
    # stopifnot(nchar(peptide) - nchar(gsub("\\.","",peptide)) == 2)
    # this one is safer, but likely to be slower
    stopifnot(all(grepl("^.\\..+\\..$", peptide)))
    #
    # remove flanking AAs
    peptide <- substring( peptide, 3, nchar(peptide)-2)
    #
    return(peptide)
}





#combined <- data.frame()
#for(i in 1:length(dirfiles)){
#      f <- dirfiles[i]
#      msnid <- MSnID(".")
#      msnid <- read_mzIDs(msnid, f)
#      combined <- rbind(psms(msnid), combined)
#}

#global <- MSnID(".")
#psms(global) <- combined

#msnid <- global

msnid <- MSnID(".")
msnid <- read_mzIDs(msnid, dirfiles)

unprocessed.msnid <- msnid

save(unprocessed.msnid, file=paste(outdir, '/msnid_unprocessed.Rdata',sep=''))

msnid <- assess_termini(msnid, validCleavagePattern="[KR]\\.[^P]")
msnid <- assess_missed_cleavages(msnid, missedCleavagePattern="[KR](?=[^P$])")

msnid$peptideSequence <- .strip_flanking_AAs(as.character(msnid$peptide))

all_descriptions <- msnid$description

#############
#Unfiltered #
#############

dir.create(paste(outdir,'/qc',sep=''),showWarnings=TRUE,recursive=FALSE,mode='0777')
jpeg(paste(outdir,'/qc/missed_cleavages.jpeg',sep=''))
pepCleav <- unique(psms(msnid)[,c("numMissCleavages", "isDecoy", "peptide")])
pepCleav <- as.data.frame(table(pepCleav[,c("numMissCleavages", "isDecoy")]))
library("ggplot2")
ggplot(pepCleav, aes(x=numMissCleavages, y=Freq, fill=isDecoy)) + geom_bar(stat='identity', position='dodge')  + ggtitle("Number of Missed Cleavages")
dev.off()

jpeg(paste(outdir,'/qc/peptide_lengths.jpeg',sep=''))
msnid$PepLength <- nchar(msnid$peptide) - 4
pepLen <- unique(psms(msnid)[,c("PepLength", "isDecoy", "peptide")])
ggplot(pepLen, aes(x=PepLength, fill=isDecoy)) + geom_histogram(position='dodge', binwidth=3) + ggtitle("Distribution of Peptide Lengths")
dev.off()

# parent ion mass measurement error (ppm)
jpeg(paste(outdir,'/qc/parent_ion_mass_measurement_error.jpeg',sep=''))
ppm <- mass_measurement_error(msnid)
ggplot(as.data.frame(ppm), aes(x=ppm))  + geom_histogram(binwidth=100)
dev.off()

# MSnID package provide a simple correct_peak_selection function that simply adds or subtracts the difference between 13C and 12C to make the error less then 1 Dalton.
jpeg(paste(outdir,'/qc/parent_ion_mass_measurement_error_corrected.jpeg',sep=''))
msnid.fixed <- correct_peak_selection(msnid)
ppm <- mass_measurement_error(msnid.fixed)
ggplot(as.data.frame(ppm), aes(x=ppm)) + geom_histogram(binwidth=0.25)
dev.off()

# recalibrate
jpeg(paste(outdir,'/qc/parent_ion_mass_measurement_error_corrected_recalibrated.jpeg',sep=''))
msnid <- recalibrate(msnid.fixed)
ppm <- mass_measurement_error(msnid)
ggplot(as.data.frame(ppm), aes(x=ppm)) +geom_histogram(binwidth=0.25)
dev.off()

# Shows how decoys distribute with error
jpeg(paste(outdir,'/qc/parent_ion_mass_measurement_error_corrected_recalibrated_stacked.jpeg',sep=''))
temp <- psms(msnid)
temp$error <- ppm
temp$ppm <- temp$error
temp$isDecoy <- msnid$isDecoy
ggplot(temp, aes(x=ppm, fill=isDecoy)) + geom_histogram(position='stack', binwidth=0.25)
dev.off()


# Lets count the number of replicates per peptide
jpeg(paste(outdir,'/qc/peptides_replicate_counts.jpeg',sep=''))
msnid.psms <- psms(msnid)
repcount <- count(msnid.psms, pepSeq, spectrumFile)
repcount <- count(repcount, pepSeq)  # ie. how many replicates per peptide
colnames(repcount)[ncol(repcount)] <- "unf.pepSeq.repcount"
msnid.psms <- merge(msnid.psms, repcount) 

msnid$unf.pepSeq.repcount <- msnid.psms$unf.pepSeq.repcount[match(msnid$pepSeq, msnid.psms$pepSeq)]


repCount <- unique(psms(msnid)[,c("pepSeq", "isDecoy", "unf.pepSeq.repcount")])
repCount <- as.data.frame(table(repCount[,c("unf.pepSeq.repcount", "isDecoy")]))
ggplot(repCount, aes(x=unf.pepSeq.repcount, y=Freq, fill=isDecoy)) + geom_bar(stat='identity', position='dodge') + ggtitle("Distribution of peptide replicate counts")
dev.off()

# PSM condifence (converted to PEP scores) 
#msnid$`PeptideShaker PSM confidence` <- as.numeric(msnid$`PeptideShaker PSM confidence`)
#msnid$PEP <- 1.0 - msnid$`PeptideShaker PSM confidence`/100.0 

#jpeg(paste(outdir,'/qc/psm_PEP.jpeg',sep=''))
#params <- psms(msnid)[,c("PEP","isDecoy")]
#ggplot(params) + geom_density(aes(x = PEP, color = isDecoy, ..count..))
#dev.off()

# PSM confidence  
msnid$`PeptideShaker PSM confidence` <- as.numeric(msnid$`PeptideShaker PSM confidence`)
jpeg(paste(outdir,'/qc/psm_confidence.jpeg',sep=''))
params <- psms(msnid)[,c("PeptideShaker PSM confidence","isDecoy")]
ggplot(params) + geom_density(aes(x="PeptideShaker PSM confidence", color = isDecoy, ..count..))
dev.off()

# PSM mass error - parent
jpeg(paste(outdir,'/qc/corrected_recalibrated_absParentMassErrorPPM.jpeg',sep=''))
msnid$absParentMassErrorPPM <- abs(mass_measurement_error(msnid))
params <- psms(msnid)[,c("absParentMassErrorPPM","isDecoy")]
ggplot(params) + geom_density(aes(x = absParentMassErrorPPM, color = isDecoy, ..count..))
dev.off()

# Parent
jpeg(paste(outdir,'/qc/corr_recal_parent_ion_mass_measurement_targetdecoy.jpeg',sep=''))
dM <- with(psms(msnid),+ (experimentalMassToCharge-calculatedMassToCharge)*chargeState) 
x <- data.frame(dM, isDecoy=msnid$isDecoy)
ggplot(x, aes(x=dM, fill=isDecoy)) +geom_histogram(position='stack', binwidth=0.1)
dev.off()



#msnid <- apply_filter(msnid, "unf.pepSeq.repcount >= 1")
#temp <- transform(psms(msnid), PEPladj = PEP / PepLength)
#msnid$PEPladj <- temp$PEPladj

show(msnid)
unfiltered <- msnid

msnid$minPepLength <- msnid$PepLength

print('Creating MSnIDFilter object:')
msnid$PeptideShakerPSMconfidence <- msnid$`PeptideShaker PSM confidence`

filtObj <- MSnIDFilter(msnid)

filtObj$absParentMassErrorPPM <- list(comparison="<", threshold=10.000)
filtObj$PeptideShakerPSMconfidence  <- list(comparison=">", threshold=80.000)

#filtObj$PepLength <- list(comparison="<", threshold=35)
#filtObj$minPepLength <- list(comparison=">", threshold=6)
#filtObj$numMissCleavages <- list(comparison="<", threshold=2)
#filtObj$numIrregCleavages <- list(comparison="<", threshold=2)
#filtObj$unf.pepSeq.repcount <- list(comparison=">=", threshold=1)

show(filtObj)
evaluate_filter(msnid, filtObj, level=fdr_level)
cat('\n')

#Protein level FDR filtering
print(paste('Applying ',fdr_level,' level FDR control: ',fdr_value,sep=''))
print('Optimizing MSnIDFilter object with "Grid" method:')
filtObj.grid <- optimize_filter(filtObj, msnid, fdr.max= fdr_value, method="Grid",level=fdr_level, n.iter=1000) 
cat('\n')

show(filtObj.grid)
show(apply_filter(msnid, filtObj.grid))

print('Optimizing MSnIDFilter.Grid object with "Nelder-Mead" method:')
filtObj.nm <- optimize_filter(filtObj.grid, msnid, fdr.max=fdr_value, method="Nelder-Mead",level=fdr_level, n.iter=1000) 
cat('\n')

show(filtObj.nm)
show(apply_filter(msnid, filtObj.nm))

print('Optimizing MSnIDFilter.NM object with "Simulated-Annealing" method:')
filtObj.sa <- optimize_filter(filtObj.nm, msnid, fdr.max=fdr_value, method="SANN",level=fdr_level, n.iter=1000) 
cat('\n')

print('Filter msnid object using the MSnIDFilter.SANN:')
msnid <- apply_filter(msnid, filtObj.sa)

show(filtObj.sa)
show(msnid)

print('...DONE APPLYING FDR STRINGENCY CRITERIA...')

# Done applying FDR filtering criteria

#############
#Filtered   #
#############

dir.create(paste(outdir,'/filtered',sep=''),showWarnings=TRUE,recursive=FALSE,mode='0777')
jpeg(paste(outdir,'/filtered/missed_cleavages.jpeg',sep=''))
pepCleav <- unique(psms(msnid)[,c("numMissCleavages", "isDecoy", "peptide")])
pepCleav <- as.data.frame(table(pepCleav[,c("numMissCleavages", "isDecoy")]))
ggplot(pepCleav, aes(x=numMissCleavages, y=Freq, fill=isDecoy)) + geom_bar(stat='identity', position='dodge')  + ggtitle("Number of Missed Cleavages")
dev.off()

jpeg(paste(outdir,'/filtered/peptide_lengths.jpeg',sep=''))
msnid$PepLength <- nchar(msnid$peptide) - 4
pepLen <- unique(psms(msnid)[,c("PepLength", "isDecoy", "peptide")])
ggplot(pepLen, aes(x=PepLength, fill=isDecoy)) + geom_histogram(position='dodge', binwidth=3) + ggtitle("Distribution of Peptide Lengths")
dev.off()

#parent ion mass measurement error (ppm)
jpeg(paste(outdir,'/filtered/parent_ion_mass_measurement_error.jpeg',sep=''))
ppm <- mass_measurement_error(msnid)
ggplot(as.data.frame(ppm), aes(x=ppm))  + geom_histogram(binwidth=100)
dev.off()

# Shows how decoys distribute with error
jpeg(paste(outdir,'/filtered/parent_ion_mass_measurement_error_stacked.jpeg',sep=''))
temp <- psms(msnid)
temp$error <- ppm
temp$ppm <- temp$error
temp$isDecoy <- msnid$isDecoy
ggplot(temp, aes(x=ppm, fill=isDecoy)) + geom_histogram(position='stack', binwidth=0.25)
dev.off()


# Lets count the number of replicates per peptide
jpeg(paste(outdir,'/filtered/peptides_replicate_counts.jpeg',sep=''))
msnid.psms <- psms(msnid)
repcount <- count(msnid.psms, pepSeq, spectrumFile)
repcount <- count(repcount, pepSeq)  # ie. how many replicates per peptide
colnames(repcount)[ncol(repcount)] <- "filt.pepSeq.repcount"
msnid.psms <- merge(msnid.psms, repcount) 
msnid$filt.pepSeq.repcount <- msnid.psms$filt.pepSeq.repcount[match(msnid$pepSeq, msnid.psms$pepSeq)]
repCount <- unique(psms(msnid)[,c("pepSeq", "isDecoy", "filt.pepSeq.repcount")])
repCount <- as.data.frame(table(repCount[,c("filt.pepSeq.repcount", "isDecoy")]))
ggplot(repCount, aes(x=filt.pepSeq.repcount, y=Freq, fill=isDecoy)) + geom_bar(stat='identity', position='dodge') + ggtitle("Distribution of peptide replicate counts")
dev.off()

# PSM condifence (converted to PEP scores) 
#jpeg(paste(outdir,'/filtered/psm_PEP.jpeg',sep=''))
#params <- psms(msnid)[,c("PEP","isDecoy")]
#ggplot(params) + geom_density(aes(x = PEP, color = isDecoy, ..count..))
#dev.off()

# PSM condifence 
jpeg(paste(outdir,'/filtered/psm_confidence.jpeg',sep=''))
params <- psms(msnid)[,c("PeptideShaker PSM confidence","isDecoy")]
ggplot(params) + geom_density(aes(x = "PeptideShaker PSM confidence", color = isDecoy, ..count..))
dev.off()

# PSM mass error - parent
jpeg(paste(outdir,'/filtered/absParentMassErrorPPM.jpeg',sep=''))
msnid$absParentMassErrorPPM <- abs(mass_measurement_error(msnid))
params <- psms(msnid)[,c("absParentMassErrorPPM","isDecoy")]
ggplot(params) + geom_density(aes(x = absParentMassErrorPPM, color = isDecoy, ..count..))
dev.off()

# Parent
jpeg(paste(outdir,'/filtered/parent_ion_mass_measurement_targetdecoy.jpeg',sep=''))
dM <- with(psms(msnid),+ (experimentalMassToCharge-calculatedMassToCharge)*chargeState) 
x <- data.frame(dM, isDecoy=msnid$isDecoy)
ggplot(x, aes(x=dM, fill=isDecoy)) +geom_histogram(position='stack', binwidth=0.1)
dev.off()

#################################
# Save MSnID files to R objects #
#################################
processed.msnid <- msnid
save(processed.msnid, file=paste(outdir,'/msnid_processed.Rdata',sep=''))

###############
## Tables     #
###############

decoy <- apply_filter(msnid, "isDecoy == TRUE")

msnid <- apply_filter(msnid, "isDecoy == FALSE")
contaminants <- apply_filter(msnid, "grepl('CONTAMINANT',accession)")
#msnid <- apply_filter(msnid, "!grepl('CONTAMINANT',description)")

contaminant.df <- psms(contaminants)
contaminant.df <- add_rownames(contaminant.df, "Row")

decoy_psm.df <- psms(decoy)
decoy_psm.df <- add_rownames(decoy_psm.df, "Row")

decoy_peptide.df <- data.frame(peptides(decoy))
decoy_peptide.df <- add_rownames(decoy_peptide.df, "Row")

decoy_accession.df <- data.frame(accessions(decoy))
decoy_accession.df <- add_rownames(decoy_accession.df, "Row")

psm.df <- psms(msnid)
psm.df <- add_rownames(psm.df, "Row")

peptide.df <- data.frame(peptides(msnid))
peptide.df <- add_rownames(peptide.df, "Row")

accession.df <- data.frame(accessions(msnid))
accession.df <- add_rownames(accession.df, "Row")

unfiltered.df <- psms(unfiltered)
unfiltered.df <- add_rownames(unfiltered.df, "Row")

table_dir <- paste(outdir, '/tables',sep='')
dir.create(table_dir, showWarnings=TRUE,recursive=FALSE,mode='0777')
write.table(psm.df, paste(table_dir, '/psms.txt',sep=''),sep='\t', row.names=FALSE)
write.table(peptide.df, paste(table_dir, '/peptides.txt',sep=''),sep='\t',row.names=FALSE)
write.table(accession.df, paste(table_dir, '/accessions.txt',sep=''),sep='\t', row.names=FALSE)

write.table(contaminant.df, paste(table_dir, '/contaminants.txt',sep=''),sep='\t', row.names=FALSE)
write.table(decoy_psm.df, paste(table_dir, '/decoy_psms.txt',sep=''),sep='\t', row.names=FALSE)
write.table(decoy_peptide.df, paste(table_dir, '/decoy_peptides.txt',sep=''),sep='\t', row.names=FALSE)
write.table(decoy_accession.df, paste(table_dir, '/decoy_accessions.txt',sep=''),sep='\t', row.names=FALSE)

write.table(unfiltered.df, paste(table_dir, '/unfiltered_psms.txt',sep=''),sep='\t', row.names=FALSE)

msnset <- as(msnid, "MSnSet")
library("MSnbase")

# Spectral counts - unique and multiple
msnset.mult <- combineFeatures(msnset, fData(msnset)$accession, redundancy.handler="multiple", fun="sum",cv=FALSE)
save(msnset.mult, file=paste(outdir , '/mult_msnset.Rdata', sep=''))
counts.mult.df <- data.frame(exprs(msnset.mult))
counts.mult.df <- add_rownames(counts.mult.df, "Row")
write.table(counts.mult.df, paste(table_dir, '/spectral_counts_multiple.txt',sep=''),sep='\t', row.names=FALSE)


msnset.unique <- combineFeatures(msnset, fData(msnset)$accession, redundancy.handler="unique", fun="sum",cv=FALSE)
save(msnset.unique, file=paste(outdir , '/unique_msnset.Rdata', sep=''))
counts.unique.df <- data.frame(exprs(msnset.unique))
counts.unique.df <- add_rownames(counts.unique.df, "Row")
write.table(counts.unique.df, paste(table_dir, '/spectral_counts_unique.txt',sep=''),sep='\t', row.names=FALSE)

#####
## Export peptides for Unipept 
####

peptides <- unique(processed.msnid$peptideSequence)
fileConn<-file(paste(outdir,"/peptides_cleaned.txt",sep=''))
writeLines(peptides, fileConn)
close(fileConn)




