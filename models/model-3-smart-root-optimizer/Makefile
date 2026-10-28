CXX ?= g++
CXXFLAGS = -O3 -std=c++17 -I src
SRCS = src/main.cpp src/Graph.cpp

ifeq ($(OS),Windows_NT)
    TARGET = RouteOptimizer_Web.exe
    RM = del /f /q
else
    TARGET = RouteOptimizer_Web
    RM = rm -f
endif

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CXX) $(CXXFLAGS) $(SRCS) -o $(TARGET)

clean:
ifeq ($(OS),Windows_NT)
	$(RM) $(TARGET) RouteOptimizer.exe
else
	$(RM) $(TARGET) RouteOptimizer
endif

.PHONY: all clean
