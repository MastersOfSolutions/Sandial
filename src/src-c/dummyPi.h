//
// Created by Ethan Randall on 12/6/16.
//

#ifndef SANDIALC_DUMMYPI_H
#define SANDIALC_DUMMYPI_H

#if !defined(__linux__)
#define wiringPiSetup() fprintf(stderr, "**SKIP**\t%s:%03d\twiringPiSetup()\n", __FILE__, __LINE__)

#define pinMode(a1, a2) fprintf(stderr, "**SKIP**\t%s:%03d\tpinMode(%s, %s)\n", \
    __FILE__, __LINE__, #a1, #a2)

#define digitalWrite(a1, a2) fprintf(stderr, "**SKIP**\t%s:%03d\tdigitalWrite(%s, %s)\n", \
    __FILE__, __LINE__, #a1, #a2)
#define delay(a1) fprintf(stderr, "**SKIP**\t%s:%03d\tdelay(%s)\n", __FILE__, __LINE__, #a1)
#endif


#endif //SANDIALC_DUMMYPI_H
