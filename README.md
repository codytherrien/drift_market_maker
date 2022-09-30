# drift_market_maker

This project can be run using exclusively python or, for better performance, a c++ binding is available. The instructions on how to build both the python and c++ builds are below. 

## Running this project with the C++ build
To run this project change the config to c++ build:
```
build_type: cpp
```

Install the requirements:
```
pip install -r requirements.txt
```

To build run 
c++ -O3 -Wall -shared -std=c++17 -fPIC $(python3 -m pybind11 --includes) MMHedge.cpp -o mmhedge_cpp$(python3-config --extension-suffix)

To run the bot: 
```
python .\trade_mm_strat.py
```

## Running this project with the Python build

To run this project change the config to python build:
```
build_type: python
```

Install the requirements:
```
pip install -r requirements.txt
```

To run the bot: 
```
python .\trade_mm_strat.py
```