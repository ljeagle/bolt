#!/bin/env/python

import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sb
import pandas as pd
import pathlib as pl

# from . import files
from . import amm_results as res


sb.set_context('poster')
# sb.set_context('talk')

RESULTS_DIR = pl.Path('results/amm')
FIGS_SAVE_DIR = pl.Path('../figs/amm')


if not os.path.exists(FIGS_SAVE_DIR):
    FIGS_SAVE_DIR.mkdir(parents=True)


def save_fig(name):
    plt.savefig(os.path.join(FIGS_SAVE_DIR, name + '.png'),
                dpi=300, bbox_inches='tight')


def _xlabel_for_xmetric(x_metric):
    return {'d': 'Sketch Size',
            'secs': 'Time (s)',
            'muls': 'Number of Multiplies',
            'nlookups': 'Number of Lookups',
            'ops': 'Number of Operations',
            'Latency': 'Latency (ms)',
            'Throughput': 'Throughput (elements/s)'}[x_metric]
    # if x_metric == 'd':
    #     return 'Log2(Sketch Size)'
    # elif x_metric == 'secs':
    #     return 'Time (s)'
    # elif x_metric == 'muls':
    #     # return 'Log10(# of Multiplies)'
    #     return 'Number of Multiplies'
    # elif x_metric == 'nlookups':
    #     # return 'Log10(# of Table Lookups)'
    #     return 'Number of Table Lookups'
    # elif x_metric == 'ops':
    #     # return 'Log10(# of Operations)'
    #     return 'Number of Operations'
    # elif x_metric == 'Latency':
    #     return 'Latency (ms)'


def _clean_results_df(df, default_D=None):
    # for Exact, set d = D
    if default_D is not None and ('d' in df):
        mask = df['d'].isna()
        df.loc[mask, 'd'] = default_D

    # clean up column names + other strings
    for old, new in [('method', 'Method'), ('acc_amm', 'Accuracy'),
                     ('r_sq', 'R-Squared'), ('nmultiplies', 'muls')]:
        try:
            df.rename({old: new}, axis=1, inplace=True)
        except KeyError:
            pass

    replace_dict = {'Bolt+MultiSplits': 'Ours',
                    'CooccurSketch': 'CD'}

    # def _replace_method_name(name):
    #     return replace_dict.get(name, name)

    df['Method'] = df['Method'].apply(lambda s: replace_dict.get(s, s))

    # create ops column that sums number of multiplies + lookups
    df['muls'] = df['muls'].fillna(0)
    mask = ~df['nlookups'].isna()
    df['ops'] = df['muls']
    df['ops'].loc[mask] += df['nlookups'].loc[mask]

    # df['muls'] = np.log10(df['muls'])
    # df['ops'] = np.log10(df['ops'])

    # join with cpp timing results
    matmul_latencies, matmul_thruputs = res.load_matmul_times_for_n_d_m()
    multisplit_latencies, multisplit_thruputs = \
        res.load_multisplit_times_for_n_d_m()
    # row_dicts = []
    all_latencies = []
    all_thruputs = []
    # for _, row in df.itertuples():

    # print("d col: ")
    # print(df['d'])

    for _, row in df.iterrows():
        # row = dict(*row)
        N, D, M = [int(row[k]) for k in ('N', 'D', 'M')]
        method = row['Method']
        # if 'split' in method.lower():
        # print("using method: ", method)
        if method.lower() in ('bolt', 'ours'):
            ncodebooks = int(row['ncodebooks'])
            N = N - (N % 32)  # TODO rm hack after gone in cpp code
            key = (N, D, M, ncodebooks)
            latencies = multisplit_latencies[key]
            thruputs = multisplit_thruputs[key]
            all_latencies.append(np.mean(latencies))
            all_thruputs.append(np.mean(thruputs))
        else:
            d = int(row['d'])
            key = (N, d, M)
            # print("d: ", d)
            latencies = matmul_latencies[key]
            thruputs = matmul_thruputs[key]
            lat = np.mean(latencies)
            thruput = np.mean(thruputs)
            # scale by number of multiplies vs exact; this is optimistic
            # because it assumes that all operations are done as efficiently
            # as in a highly optimized matmul routine (you could maybe argue
            # that latency might not scale linearly, but all the methods for
            # which this applies are so far from being competitive that I
            # kind of don't care)
            if method != 'Exact':
                nmuls = int(row['muls'])
                exact_nmuls = N * D * M
                scale = nmuls / exact_nmuls
                # print("N, D, M, d", N, D, M, d)
                # print("method, scale", method, scale)
                # assert(scale > 1)
                lat *= scale
                thruput /= scale
            all_latencies.append(lat)
            all_thruputs.append(thruput)

    # print("len latencies: ", len(all_latencies))
    # print("len thruputs: ", len(all_thruputs))
    # print("df len: ", df.shape[0])
    df['Latency'] = all_latencies
    df['Throughput'] = all_thruputs

    # make stuff log scale
    # if 'd' in df:
    #     df['d'] = np.log2(df['d']).astype(np.int32)
    df['Log10(MSE)'] = np.log10(1. - df['R-Squared'] + 1e-10)

    return df


def make_cifar_fig(x_metric='d', y_metric='Accuracy'):
    # fig, axes = plt.subplots(2, 1, figsize=(6, 9), sharex=True)
    fig, axes = plt.subplots(2, 1, figsize=(11, 13.5), sharex=True)

    df10 = pd.read_csv(RESULTS_DIR / 'cifar10.csv')
    df100 = pd.read_csv(RESULTS_DIR / 'cifar100.csv')
    # dfs = (df10, df100)

    # for df in dfs:
    if x_metric in ('Latency', 'Throughput'):
        # TODO get results for PQ + Bolt
        df10 = df10.loc[~df10['method'].isin(['PQ', 'Bolt'])]
        df10 = df10.loc[~(df10['ncodebooks'] < 4)]
        df100 = df100.loc[~df100['method'].isin(['PQ', 'Bolt'])]
        df100 = df100.loc[~(df100['ncodebooks'] < 4)]

    df10 = _clean_results_df(df10, default_D=512)
    df100 = _clean_results_df(df100, default_D=512)

    def lineplot(data, ax):
        sb.lineplot(data=data, hue='Method', x=x_metric, y=y_metric,
                    style='Method', markers=True, dashes=False, ax=ax)

    lineplot(df10, axes[0])
    lineplot(df100, axes[1])

    # plt.suptitle('Sketch size vs Classification Accuracy')
    xlbl = _xlabel_for_xmetric(x_metric)
    # plt.suptitle('{} vs {}'.format(xlbl, y_metric))
    plt.suptitle('Approximating Softmax Layers')
    axes[0].set_title('CIFAR-10')
    for ax in axes:
        ax.set_ylabel(y_metric)
    axes[0].set_xlabel(None)
    axes[1].set_xlabel(xlbl)
    axes[1].set_title('CIFAR-100')

    handles, labels = axes[0].get_legend_handles_labels()
    handles, labels = handles[1:], labels[1:]  # rm 'Method' title
    # axes[0].legend(handles, labels, fontsize='small')
    axes[1].legend(handles, labels, fontsize='small')
    # plt.figlegend(handles, labels, loc='lower center', ncol=1)
    # plt.figlegend(handles, labels, loc='center right', ncol=1)
    axes[0].get_legend().remove()
    # axes[1].get_legend().remove()

    if x_metric in ('muls', 'ops', 'nlookups', 'Latency', 'Throughput'):
        axes[0].semilogx()

    plt.tight_layout()
    # plt.subplots_adjust(top=.92, bottom=.2)
    plt.subplots_adjust(top=.92, bottom=.22)
    save_fig('cifar_{}_{}'.format(x_metric, y_metric))


# def make_ecg_fig(y_metric='R-Squared'):
def make_ecg_fig(x_metric='d'):
    fig, axes = plt.subplots(2, 1, figsize=(6, 9))
    df = pd.read_csv(RESULTS_DIR / 'ecg.csv')
    df = _clean_results_df(df, default_D=24)

    # D = 24

    # if 'd' in df:
    #     mask = df['d'].isna()
    #     df.loc[mask, 'd'] = D
    #     df['d'] = np.log2(df['d'])
    # df.rename({'method': 'Method', 'acc_amm': 'Accuracy',
    #            'r_sq': 'R-Squared', 'nmultiplies': 'muls'},
    #           axis=1, inplace=True)
    # df['Log10(MSE)'] = np.log10(1. - df['R-Squared'] + 1e-10)  # avoid log10(0)
    # df['muls'] = df['muls'].fillna(0)
    # df['nlookups'] = df['nlookups'].fillna(0)
    # # mask = ~df['nlookups'].isna()
    # # print("mask: ", mask)

    # # print('muls, nlookups')
    # # print(df[['muls', 'nlookups']])

    # # add_to_muls = df['nlookups'].loc[mask]

    # equivalent_muls = df['muls'].add(df['nlookups'])
    # # df['muls'] = equivalent_muls
    # df['muls'] = equivalent_muls

    # # import sys; sys.exit()
    # df['muls'] = np.log10(df['muls'])

    df['Compression Ratio'] = df['nbytes_orig'] / df['nbytes_blosc_byteshuf']

    def lineplot(data, ycol, ax):
        sb.lineplot(data=data, hue='Method', x=x_metric, y=ycol,
                    style='Method', markers=True, dashes=False, ax=ax)

    lineplot(df, ycol='R-Squared', ax=axes[0])
    lineplot(df, ycol='Compression Ratio', ax=axes[1])

    xlbl = _xlabel_for_xmetric(x_metric)
    axes[0].set_title('ECG: {} vs R-Squared'.format(xlbl))
    axes[1].set_title('ECG: {} vs Compression Ratio'.format(xlbl))
    axes[0].set_ylim([0, 1])
    axes[0].set_ylabel('R-Squared')
    axes[1].set_ylabel('Compression Ratio')
    axes[1].set_xlabel(xlbl)

    if x_metric in ('muls', 'ops', 'nlookups'):
        axes[0].semilogx()
        # axes[0].semilogx()

    plt.tight_layout()
    plt.subplots_adjust(top=.92, bottom=.2)
    save_fig('ecg_{}'.format(x_metric))


def make_caltech_fig(x_metric='d'):
    """x_metric should be in {'d', 'secs', 'muls'}"""

    fig, ax = plt.subplots(1, 1, figsize=(6, 6))
    df = pd.read_csv(RESULTS_DIR / 'caltech.csv')
    df = _clean_results_df(df, default_D=27)

    sb.lineplot(data=df, hue='Method', x=x_metric, y='Log10(MSE)',
                style='Method', markers=True, dashes=False, ax=ax)

    ax.set_ylabel('Log10(MSE + 1e-10)')
    if x_metric == 'd':
        ax.set_title('Caltech: Sketch Size vs Log Squared Error')
        ax.set_xlabel('Log2(Sketch Size)')
    elif x_metric == 'secs':
        ax.set_title('Caltech: Computation Time vs Log Squared Error')
        ax.set_xlabel('Time (s)')
    elif x_metric == 'muls':
        ax.set_title('Caltech: # of Multiplies vs Log Squared Error')
        ax.set_xlabel('Log10(# of Multiplies)')
    plt.tight_layout()
    plt.subplots_adjust(top=.92, bottom=.2)
    save_fig('caltech_{}'.format(x_metric))


def main():
    # for x_metric in 'd secs muls'.split():
    # for x_metric in ['muls']:
    #     for y_metric in ('Accuracy', 'R-Squared'):
    #         make_cifar_fig(x_metric, y_metric)
    # make_cifar_fig('d', 'Accuracy')
    # make_cifar_fig('muls', 'Accuracy')
    # make_cifar_fig('ops', 'Accuracy')
    # make_cifar_fig('Latency', 'Accuracy')
    make_cifar_fig('Throughput', 'Accuracy')
    # make_cifar_fig('Accuracy')
    # make_cifar_fig('Accuracy')
    # make_cifar_fig('R-Squared')
    # make_ecg_fig(x_metric='d')
    # make_ecg_fig(x_metric='secs')
    # make_ecg_fig(x_metric='muls')
    # make_caltech_fig(x_metric='d')
    # make_caltech_fig(x_metric='secs')
    # make_caltech_fig(x_metric='muls')
    print("done")


if __name__ == '__main__':
    main()
