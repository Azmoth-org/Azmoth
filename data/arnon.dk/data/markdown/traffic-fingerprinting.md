# Malicious traffic detection using traffic fingerprints and machine learning

- **URL:** https://arnon.dk/traffic-fingerprinting/
- **Author:** Arnon Shimoni
- **Published:** 2015-01-19T13:05:54+00:00
- **Modified:** 2022-06-13T17:00:52+00:00
- **Type:** post
- **Topics:** Network Security
- **Tags:** algorithm, ben gurion, bgu, botnet, capture, cryptolocker, fingerprint, machine learning, malware, ml, network, python, security, supervised learning, university, virus
- **Reading time:** 1 minute
- **Description:** Over the past year, we’ve worked on a machine learning project at Ben Gurion University of the Negev. The project attempted to find out if we can identify malicious underlying traffic (viruses, botnets, command and control channels) hiding interspersed in ‘normal’ network traffic, without using advanced heuristics or deep packet inspection – but by using […]

Over the past year, we’ve worked on a machine learning project at Ben Gurion University of the Negev.

The project attempted to find out if we can identify malicious underlying traffic (viruses, botnets, command and control channels) hiding interspersed in ‘normal’ network traffic, without using advanced heuristics or deep packet inspection – but by using the statistical breakdown of the packets and supervised machine learning algorithms, as well as clustering.

By using inter-arrival and departure times of the packets seen on a network connection in conjunction with the

Lempel Ziv 78

(LZ78) compression algorithm to assign probabilities, we arrived at some interesting results.

This means that even malware which transports data through TLS encrypted flow can be identified, without decrypting the data first.

The article was originally to be published in November 2014, but we missed several deadlines. Instead of having it be buried in my files, I’ve attached the article for any and all interested.

The research paper

Malicious traffic detection using traffic fingerprint (PDF, 6MB)

Our Python3 source code

https://github.com/arnons1/trafficfingerprint
