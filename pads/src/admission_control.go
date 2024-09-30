package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
)

func main() {
	var requirementsFilePath string

	flag.StringVar(&requirementsFilePath, "r", "", "Provide application requirement json file")

	flag.Parse()

	// fmt.Println(requirementsFilePath)

	jsonFile, err := os.Open(requirementsFilePath)

	if err != nil {
		fmt.Printf("Application requirement file could not been read\n")
	}

	defer jsonFile.Close()

	byteValue, _ := io.ReadAll(jsonFile)

	var result map[string]interface{}          // a map where the keys are strings, and the values can be of any type.
	json.Unmarshal([]byte(byteValue), &result) // decodes the JSON data contained in the `byteValue` variable and stores the result in the `result` variable.

	fmt.Printf("Application type: %s\n", result["application_type"])
	fmt.Printf("Application SLO: %v\n", result["application_slo_requirement"])
	// fmt.Println(reflect.TypeOf(result["application_slo_requirement"]))
	// fmt.Println(result["application_image_path"])
}

func createInstance(imagePath string) {
	// Connect to Incus over the Unix socket
	c, err := incus.ConnectIncusUnix("", nil)
	
	if err != nil {
		return err
	}

	// Instance creation request
	req := api.InstancesPost{
	Name: "incus-test-container-1",
	Source: api.InstanceSource{
		Type:  "image",
		Alias: "my-image",
	},
	Type: "container"
	}

	// Get Incus to create the instance (background operation)
	op, err := c.CreateInstance(req)
	
	if err != nil {
		return err
	}

	// Wait for the operation to complete
	err = op.Wait()
	if err != nil {
		return err
	}

	// Get Incus to start the instance (background operation)
	reqState := api.InstanceStatePut{
	Action: "start",
	Timeout: -1,
	}

	op, err = c.UpdateInstanceState(name, reqState, "")
	
	if err != nil {
		return err
	}

	// Wait for the operation to complete
	err = op.Wait()
	
	if err != nil {
		return err
	}
}
