import os 
import json
import random
import argparse

import numpy as np
import matplotlib.pyplot as plt 

from treebank import TripleStore
from peranto_triples import PerantoTripleStore

SRC_PATH  = os.getcwd()
MAIN_PATH = os.path.dirname(SRC_PATH)
PER_PATH  = os.path.dirname(MAIN_PATH)

class Config:
    """
    Config configures an Experiment (see below). Each experiment
    grid searches through strength/discount pairs in order to tune a 
    specific distribution. 

    So, to configure an Experiment you need to specify a distribution
    and a input_space, which is a dict mapping "Strength" and "Discount"
    to a list of strengths/discounts to search through. You also need 
    to specify a folder to save the data in, as well as a base json peranto
    config file to reference (should be located in experiment_data/base_file)
    """
    def __init__(self,
        distribution: str,
        input_space       = None,
        base_file  :  str = "basefile.json",
        data_folder:  str = "experiment",
        child_dists: list = None
        ):

        self.distribution = distribution

        if input_space is None:
            input_space: dict = {
            "Strength" : list(np.arange(0, 1050, 50)),
            "Discount" : list(np.arange(0, 1, .1))
            }

        self.input_space = input_space
        self.base_file   = base_file 
        self.data_folder = data_folder

        if child_dists is None:
            self.child_dists = [distribution]
            # child_dist_map = {
            #     'nn'          : ['nn', 'nn.arg0', 'nn.arg1', 'nn.arg0.$y0', 'nn.arg1.$y0'],
            #     'vb'          : ['vb'],
            #     'nn.arg0'     : ['nn.arg0', 'nn.arg0.$y0'],
            #     'nn.arg1'     : ['nn.arg1', 'nn.arg1.$y0'],
            #     'nn.arg0.$y0' : ['nn.arg0.$y0'],
            #     'nn.arg1.$y0' : ['nn.arg1.$y0']
            #     }
            #self.child_dists = child_dist_map[distribution]

class Experiment:
    """
    An Experiment grid searches through strength/discount pairs for
    a given distribution. There are two key functionalities of the 
    Experiment.

    First, one should call:

    exp = Experiment(config)
    exp.setup()

    Setup will do 3 things:
        (1) Creates parameters/{dist}_params.txt file containing strength/discount pairs 
        (2) Create a bunch of testperanto config json files
            - located in json_data/{dist}
            - filenames are {dist}_amr_s{strength}_d{discount}.json
            - each modifies some base json file to specific strength/discount 
        (3) Creates sh_scripts/{dist}.sh, which is a shell script to run all created json files

    Once this shell script is created, one should run the sh script on appa:
        sbatch {dist}.sh

    This script will create peranto_output/{dist}/peranto_{dist}_s{str}_d{dis}.txt, containing
    peranto output. This will take awhile (if num_sentences = 5897 ~ 2.5hr). Afterwards you should call

    exp.run()

    Run will do  things:
        (1) Cleans each peranto output file to be in the correct form
            - for example if dist == nn the cleaned file will only have nouns 
        (2) Computes the singleton proportion of each peranto output (along with treebank data)
        (3) Computes and saves the MSE between treebank and each peranto output
            - Saved in mse_results/{dist}_mse_results.txt
        (4) Saves a plot of the singleton proportion of the top k params and treebank data 
            - Saved in plots/{dist}_curves.jpg
    """
    distributions = [
            'nn', 'vb',
            'nn.arg0', 'nn.arg1', 
            'nn.arg0.$y0', 'nn.arg1.$y0'
            ]

    def __init__(self, config: Config):
        self.dist        = config.distribution
        self.name        = self.dist.replace("$","")                # avoids sh scripts error 
        self.input_space = config.input_space 
        self.child_dists = config.child_dists
        self.num_pron    = (0.6981516025097507, 0.2518229608275394) # subj prop, obj prop
        self.store       = TripleStore()
        self.data_path   = f"{MAIN_PATH}/experiment_data/{config.data_folder}"
        self.base_file   = f"{MAIN_PATH}/experiment_data/{config.base_file}"
        self.param_path  = f"{self.data_path}/parameters/{self.name}_params.txt"
        self.json_path   = f"{self.data_path}/json_data/{self.name}"
        self.sh_path     = f"{self.data_path}/sh_scripts"
        self.output_path = f"{self.data_path}/peranto_output"
        self.mse_path    = f"{self.data_path}/mse_results"
        self.plot_path   = f"{self.data_path}/plots"
        self.initialize()

    def initialize(self):
        """Initializes the configuration with some basic checks"""
        if not self.dist in self.distributions:
            raise Exception("config.distribution must be either 'vb', 'nn', 'nn.arg0', 'nn.arg1', 'nn.arg0.$y0', or 'nn.arg1.$y0'")

        if not list(self.input_space.keys()) == ['Strength', 'Discount']:
            raise Exception("config.input_space but have keys Strength/Discount")
        
        for val in self.input_space.values():
            if not isinstance(val, list):
                print(val)
                print(type(val))
                raise Exception("config.input_space values must be lists")

        if not os.path.exists(self.base_file):
            raise Exception(f"{self.base_file} path doesn't exist")
    
        paths = [
            self.data_path,
            f"{self.data_path}/parameters",
            self.json_path,
            self.sh_path,
            f"{self.output_path}/{self.name}",
            f"{self.output_path}/{self.name} modified",
            self.mse_path,
            self.plot_path
            ]

        ### create paths
        for path in paths:
            if not os.path.exists(path):
                os.makedirs(path)

        ### tune lvl1 before lvl2 before lvl3
        get_param_path = lambda dist : f"{self.data_path}/parameters/{dist}_params.txt"
        lvl1_dist = ['vb', 'nn']
        lvl2_dist = ["nn.arg0", 'nn.arg1']
        lvl3_dist = ['nn.arg0.y0', 'nn.arg1.y0']

        if self.name in lvl3_dist:
            for dist in lvl1_dist + lvl2_dist:
                if not os.path.exists(get_param_path(dist)):
                    raise Exception(f"Please tune {dist} before {self.name}")
        
        if self.name in lvl2_dist:
            for dist in lvl1_dist:
                if not os.path.exists(get_param_path(dist)):
                    raise Exception(f"Please tune {dist} before {self.name}")

    def create_param_space(self):
        """
        Given input space {"Strength" : [strengths], "Discount" : [discounts]}
        this function creates a parameters.txt file that contains all (S, D) pair
        """
        # generate pairs
        inputs = self.input_space
        pairs = [(strength, discount) for strength in inputs["Strength"] for discount in inputs["Discount"]]

        # Create parameters.txt file and write in paramaters
        with open(self.param_path, "w") as f:
            for pair in pairs:
                f.write(f"{pair[0]}, {pair[1]}\n")

    def create_json_configs(self):
        """
        Uses output from create_param_space() input space (create_input_space()) and 
        for each (S,D) pair copies the amr_tuned.json file and changes the 
        strength/discount to (S,D). All of this is saved in a folder of json files
        """

        json_file_to_read = self.base_file


        zdists = {
            "nn"          : ['nn'],
            'nn.arg0'     : ['nn.$y1'],
            'nn.arg1'     : ['nn.$y1'],
            'nn.arg0.$y0' : ['nn.$y1.$y2'],
            'nn.arg1.$y0' : ['nn.$y1.$y2']
            }

        with open(self.param_path, "r") as f:
            lines = f.readlines()
            parameters = [(float(line.split(",")[0].strip()), float(line.split(",")[1].strip())) for line in lines]
        
        # Read the original JSON content
        with open(json_file_to_read, "r") as f:
            json_content = json.load(f)

        for strength, discount in parameters:
            # modify pyor dists as appropriate
            for dist in json_content["distributions"]:
            # modify appropriate parameters, according to the distribution
                if dist["name"] in self.child_dists:
                    dist['strength'] = strength
                    dist['discount'] = discount 

            # set proportion of pronouns as appropriate  
            for rule in json_content["rules"]:
                if self.dist != 'vb' and rule['rule'] == "$qentity.$y1.$y2 -> (ENTITY $qnn.$y1.$z1 $qentitymods)":
                    rule['zdists'] = zdists[self.dist]
                if rule["rule"] == "$qnn.arg0.$y1 -> (inst nn.$y1)":
                    rule["base_weight"] = float(1 - self.num_pron[0])
                if rule["rule"] == "$qnn.arg0.$y1 -> (inst pron.$z1)":
                    rule["base_weight"] = float(self.num_pron[0])
                if rule["rule"] == "$qnn.arg1.$y1 -> (inst nn.$y1)":
                    rule["base_weight"] = float(1-self.num_pron[1])
                if rule["rule"] == "$qnn.arg1.$y1 -> (inst pron.$z1)":
                    rule["base_weight"] = float(self.num_pron[1])
            
            # Save the modified JSON content to a new file
            new_file_name = f"{self.json_path}/{self.name}_amr_s{int(strength)}_d{int(discount*100)}.json"
            with open(new_file_name, "w") as f:
                json.dump(json_content, f, indent=4)

    def create_sh_script(self):
        """
        runs the .sh script created by create_sh_script()
        """
        script_name = f"{self.sh_path}/{self.name}.sh"

        shell_script_content = f"""#!/bin/sh
        #SBATCH -c 64                # Request 64 CPU core
        #SBATCH -t 0-02:00          # Runtime in D-HH:MM, minimum of 10 mins
        #SBATCH -p dl               # Partition to submit to 
        #SBATCH --mem=10G           # Request 10G of memory
        #SBATCH -o {self.name}.out  # File to which STDOUT will be written
        #SBATCH -e error.err        # File to which STDERR will be written
        #SBATCH --gres=gpu:0        # Request 0 GPUs

        JSON_PATH="{self.json_path}"
        DATA_PATH="{self.output_path}"
        PERANTO_PATH="{PER_PATH}"

        find "$JSON_PATH" -name '{self.name}_amr_*.json' | xargs -I {{}} -P 64 bash -c '
            json_file="$1"
            strength=$(echo "$json_file" | grep -o -E "s[0-9]+" | sed "s/s//")
            discount=$(echo "$json_file" | grep -o -E "d[0-9]+" | sed "s/d//")
            python "'"$PERANTO_PATH"'/scripts/generate.py" -c "$json_file" "'"$PERANTO_PATH"'/examples/svo/middleman1.json" "'"$PERANTO_PATH"'/examples/svo/english1.json" --sents -n 5897 > "'"$DATA_PATH"'/{self.name}/peranto_{self.name}_s${{strength}}_d${{discount}}.txt"
        ' _ {{}}
        """

        with open(script_name, 'w') as script_file:
            script_file.write(shell_script_content)
    
    def setup(self):
        """
        One-stop shop for creating all necessary files and sh scripts for an expirament. 
        Note that the base file argument determins which previous previous paramater settings are 
        used to generate json files for subsequent iterations of tuning.
        """
        self.create_param_space()
        self.create_json_configs()
        self.create_sh_script()
        print(f'Experiment setup completed. Please run shell script on appa.')

    def get_peranto_data(self):
        """
        Overwrites Testperanto generated output files to only contain relevant information
        based on the distribution that is being tuned.
        """
        peranto_data = {}
        # iterate through all files 
        with open(self.param_path, "r") as f:
            lines = f.readlines()
            parameters = [(float(line.split(",")[0].strip()), float(line.split(",")[1].strip())) for line in lines]
    
        for strength, discount in parameters:
            file_path = f"{self.output_path}/{self.name}/peranto_{self.name}_s{int(strength)}_d{int(100* discount)}.txt"
            store = PerantoTripleStore() 
            try:
                with open(file_path, 'r') as file:
                    for line in file.readlines():
                        line = line.split()
                        subject = line[0]
                        verb = line[1]
                        obj= line[2]
                        store.add_triple(subject, verb, obj)      
            except FileNotFoundError:
                print(f"The file at path {file_path} was not found.")
                return None
            except Exception as e:
                print(f"An error occurred: {str(e)}")

                return None
            stuff_to_write = store.get(self.dist)  
            peranto_data[(strength, discount)] = stuff_to_write.copy()
            # write filtered content to files

            try:
                file_name = f"{self.output_path}/{self.name} modified/peranto_{self.name}_s{int(strength)}_d{int(100* discount)}_modified.txt"
                with open(file_name, 'w') as file:
                    # Iterate through each tuple in the list
                    for tup in stuff_to_write:
                        # Iterate through each item in the tuple
                        for item in tup:
                            # Write each item on a line separated by space 
                            file.write(str(item) + " ")
                        # Add an newline for separation between tuples
                        file.write("\n")
            except Exception as e:
                print(f"An error occurred: {str(e)}")

        return peranto_data

    def get_singleton_prop(self):
        """
        Computes singleton proportion for treebank and generated data.
        First creates a lst singletons s.t. singletons[i] = num singletons in data[:i]
        Then normalizes with len(data[:i]).

        Returns tuple of the form
            {(str, dis) : [singleton prop], (str1, dis1) : [singleton prop1], ...},
            [singleton prop of treebank data]
        """
        data = self.get_peranto_data() # {(strength, discount) : [(he, eat), (my, name), ...]} 

        def get_prop(lst):
            singleton_count = 0
            seen = set()
            singletons = []
            total = []

            if len(lst[0]) == 1: # self.dist in [nn, vb, nn.arg0, nn.arg1]
                # the isinstance checks in case data is (strength, discount) : ['he', 'my', ...]
                lst = [(x, x) for x in lst] # this just makes things convenient

            for idx, (a, b) in enumerate(lst):
                if (a, b) not in seen: # singleton
                    singleton_count += 1
                    seen.add((a, b))
                singletons.append(singleton_count)
                total.append(idx + 1)

            singleton_prop = np.array(singletons) / np.array(total)
            return singleton_prop

        peranto_prop = {(str, dis) : get_prop(lst) for (str, dis), lst in data.items()}
        treebank_prop = get_prop(self.store.get(self.dist))
        
        return peranto_prop, treebank_prop

    def get_top_k(self, singleton_prop, treebank_prop, k=10):
        """
        Computes and saves the MSE between treebank prop and each 
        singleton_prop of generated data. Returns a list of the top
        k (str, dis) params, measured by MSE. 
        """
        def mse(x, y):
            return np.mean((x-y)**2)

        mse_results = {(str, dis) : mse(treebank_prop, sing_prop)
                        for (str, dis), sing_prop in singleton_prop.items()}

        mse_results = sorted(mse_results.items(), key = lambda x : x[1]) # sort by mse
        try:
            file_path = f"{self.mse_path}/{self.name}_mse_results.txt"
            with open(file_path, 'w') as file:
                for (strength, discount), mse in mse_results:
                    file.write(f"S ={str(strength)}, D={str(discount)} MSE: {mse}")
                    file.write("\n")

        except Exception as e:
            print(f"An error occurred: {str(e)}")
        res = [[(str, dis), mse] for (str, dis), mse in mse_results][:k]
        return {x[0] : x[1] for x in res} #maps (str, dis) => mse

    def create_plot(self, singleton_prop, treebank_prop, best_params):
        """
        Creates and saves a plot of the singleton proportion curves of the 
        top k (str, dis) pairs.
        """
        plt.figure(figsize=(10, 6))
        
        data = {}

        for (str, dis), mse in best_params.items():
            curve = singleton_prop[(str, dis)]
            name = f"S={str},D={round(dis, 3)},MSE={round(mse, 4)}"
            data[name] = curve
        
        data["Treebank"] = treebank_prop

        for name, curve in data.items():
            plt.plot(list(range(1, len(curve) + 1)), curve, label=name)
            
        dist_map = {
            "nn"          : "Nouns",
            "vb"          : "Verbs",
            'nn.arg0'     : "Subjects",
            "nn.arg1"     : "Objects",
            "nn.arg0.$y0" : "Subject Verb Pairs",
            "nn.arg1.$y0" : "Verb Object Pairs"
        }
        plt.title(f"Singleton Proportion for {dist_map[self.dist]}")
        plt.xlabel("Total Number of Entries")
        plt.ylabel("Singleton Proportion")
        plt.legend(loc='upper left', bbox_to_anchor=(1, 1))
        plt.grid(True)

        path = f"{self.plot_path}/{self.name}_curves.jpg"
        plt.savefig(path,bbox_inches="tight")
        plt.show()
    
    def run(self, k=10):
        singleton_prop, treebank_prop = self.get_singleton_prop()
        best_params = self.get_top_k(singleton_prop, treebank_prop, k)
        self.create_plot(singleton_prop, treebank_prop, best_params)

def main():
    parser = argparse.ArgumentParser(description='Experiment parser')
    parser.add_argument(
            '-d', '--distribution',
            type=str,
            required=True,
            help='Distribution: must be nn, nn.arg0, nn.arg1, nn.arg0.$y0, nn.arg1.$y0'
            )
    
    parser.add_argument(
            '-f', '--folder',
            type=str,
            required=False,
            default="experiment",
            help='Specify the folder name to save data'
            )

    parser.add_argument(
            '-s', '--setup',
            action='store_true',
            help='If True, calls exp.setup()'
            )

    parser.add_argument(
            '-r', '--run',
            action='store_true',
            help='If True, calls exp.run()'
            )

    parser.add_argument(
            '-b', '--basefile',
            type=str,
            required=False, 
            default="basefile.json",
            help='specify the base json config file'
            )

    parser.add_argument(
            '-k',
            type=int,
            required=False, 
            default=3,
            help='num curves to plot'
            )

    args = parser.parse_args()

    config = Config(
        args.distribution, 
        data_folder=args.folder,
        base_file=args.basefile
        )
    
    exp = Experiment(config)

    if args.setup:
        exp.setup()
    else:
        exp.run(k=args.k)

if __name__ == "__main__":
    main()

"""
Usage:

python experiment.py -d "nn" -f "new" -s (to setup)
python experiment.py -d "nn" -f "new" -r (to run)
"""