import itertools
import os

class PerantoTree:
    """
    PerantoTree specifies a tree of files that config testperanto
    """

    def __init__(self, 
            json_path,
            amr_files,
            middleman_files,
            language_files,
            names
            ):

        self.amr_paths    = [f'{json_path}/amr_files/{amr_file}.json' for amr_file in amr_files]
        self.middle_paths = [f'{json_path}/middleman_files/{mid_file}.json' for mid_file in middleman_files]
        self.lang_paths   = [f'{json_path}/language_files/{lang_file}.json' for lang_file in language_files]
        self.lang_paths  += self.lang_paths # duplicate to allow for identity mapping
        self.data         = [self.amr_paths, self.middle_paths, self.lang_paths]
        self.names        = names #[SVO, OVS, ...]
        self.dup_names    = [f'{name}1' for name in names] # duplicate for identity mapping

        self.file_order = {i : name for i, name in enumerate(self.names + self.dup_names)} # SVO,  ..., SVo1, 
        self.num_paths  = len(self.amr_paths) * len(self.middle_paths) * len(self.lang_paths)

    def get(self):
        return self.data

    def get_names(self):
        return self.names

class Config:
    ### TO DO: check if from/to_dict are working/add reinitialization 
    
    def __init__(self): 
        self.exp_name     = 'svo_permutations'                              # exp name (don't put spaces or slashes or weird crap)

        ### path configurations
        self.SRC_PATH     = os.getcwd()                                     # src code
        self.MAIN_PATH    = os.path.dirname(self.SRC_PATH)                  # main experiment_pipeline path
        self.PERANTO_PATH = os.path.dirname(self.MAIN_PATH)                 # testperanto main path
        self.DATA_PATH    = f"{self.MAIN_PATH}/experiment_data"             # data path
        self.EXP_PATH     = f"{self.DATA_PATH}/experiments/{self.exp_name}" # path for this experiment
        self.TRAIN_PATH   = f"{self.EXP_PATH}/data"                         # for train/test/dev sets
        self.RESULTS_PATH = f'{self.EXP_PATH}/results'                      # for model results
        self.APPA_PATH    = f"{self.PERANTO_PATH}/appa-mt/fairseq"          # for appa fairseq training
        self.JSON_PATH    = f"{self.DATA_PATH}/peranto_files"               # contains 3 folders w/ tp config 
        self.OUT_PATH     = f"{self.EXP_PATH}/output"                       # path for generated data 
        self.YAML_FPATH   = f"{self.EXP_PATH}/{self.exp_name}.yaml"         # yaml filepath (filepath so don't os.makedirs)
        self.SH_FPATH     = f"{self.EXP_PATH}/{self.exp_name}.sh"           # sh filepath 

        ### data generator configs
        self.peranto_tree = PerantoTree(                                    # PerTree to config parallel_gen.py
            json_path       = self.JSON_PATH,                               # contains amr_files, middleman_files, language_files folders
            amr_files       = ['amr'],                                      # json_path/amr_files/amr.json
            middleman_files = ['middleman'],                                # json_path/middleman_files/middleman.json
            language_files  = [f"english{''.join(p)}"                       # json_path/language_files/englishSVO.json ...
                                 for p in itertools.permutations("SVO")],
            names           = ['SVO', 'SOV', 'VSO', 'VOS', 'OSV', 'OVS']
            )

        self.corp_lens    = [1000 * (2 ** i) for i in range(10)]            # 1000, 2000, ..., 512000
        self.num_cores    = 32
       
        ### data processor configs 
        self.num_trans    = 2                                               # if 2 takes pairs of languages, 3 triples, ...
        combos = list((itertools.combinations(self.peranto_tree.names, self.num_trans)))
        id_maps = [(name, f"{name}1") for name in self.peranto_tree.names]
        self.combos       = combos + id_maps
        self.train_size   = .8
        self.test_size    = .1
        self.dev_size     = .1

        ### trainer configs
        self.num_epochs = 750
        self.num_gpus   = 2
        self.patience   = 30

        self.initialize()

    def initialize(self):
        paths = [
            self.SRC_PATH,
            self.MAIN_PATH,
            self.PERANTO_PATH,
            self.DATA_PATH,
            self.EXP_PATH,
            self.JSON_PATH,
            self.OUT_PATH,
            self.TRAIN_PATH,
            self.RESULTS_PATH,
            f"{self.OUT_PATH}/temporary"
            ]
        
        for path in paths:
            os.makedirs(path, exist_ok=True)

        ### check json_path has correct subfolders 

    def from_dict(self, config_dict):
        """
        Update configuration from a dictionary.
        """
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.initalize()

    def to_dict(self):
        """
        Convert configuration to a dictionary.
        """
        return self.__dict__
    
    def __repr__(self):
        return str(self.to_dict())


if __name__ == '__main__':
    pass 