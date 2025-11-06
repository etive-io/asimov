asimovversion=$(asimov --version | tail -n 1 | cut  -d " " -f 3)
codename="asimov-$asimovversion"

# ACCESS_TOKEN=$(cat token)

rm -rf $codename
#rm -rf ~/public_html/asimov-review/daniel/$codename

mkdir $codename
cd $codename
asimov init $codename

asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/testing-pe-osg.yaml
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/cbcflow.yaml
asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/defaults/production-pe-priors.yaml

asimov configuration update condor/user daniel.williams

asimov apply -f https://git.ligo.org/asimov/data/-/raw/main/events/gwtc-2-1/GW150914_095045.yaml
asimov apply -f ../blueprints/analyses.yaml -e S230608as

asimov manage build
# asimov manage submit

# asimov start
