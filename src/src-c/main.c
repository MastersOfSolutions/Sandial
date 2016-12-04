//
//  main.c
//
//
//  Created by RS on 11/29/16.
//
//

#include <stdio.h>
#include <wiringPi.h>

#define LED_PIN 1

int main()
{
    printf("\n\n Hello World! \n\n");

    //instantiate wiringPi
    wiringPiSetup();

    //setup pins
    pinMode(LED_PIN, OUTPUT);

    int count = 0;
    while(count++ < 10)
    {
        digitalWrite(LED_PIN, HIGH);
        delay(500);
        digitalWrite(LED_PIN, LOW);
        delay(500);
    }

    return 0;
}
