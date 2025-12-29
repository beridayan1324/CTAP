// ===== ESP32 PIN CONFIG =====
int piezoPins[] = {34, 35, 32, 33};  // 3 fingers + SEND (Space)
int numPiezos = 4;

int ledPin = 2;

// ===== SETTINGS =====
int thresholdDrop = 200;
int baseline = 800;
unsigned long debounceTime = 50;
unsigned long letterWait = 200;

// ===== STATE =====
int lastReading[4] = {0};
unsigned long lastHitTime[4] = {0};

bool fingerHit[3] = {false, false, false};
unsigned long firstHitTime = 0;

// Track consecutive space hits
int spaceHitCount = 0;

// Accumulated binary sentence
String binarySentence = "";

void setup() {
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  Serial.println("CTAP Serial-Only Mode Ready");
}

void loop() {
  unsigned long now = millis();

  // --- read piezos ---
  for (int i = 0; i < numPiezos; i++) {
    int reading = analogRead(piezoPins[i]);
    int drop = lastReading[i] - reading;

    if (
      lastReading[i] >= baseline &&
      drop >= thresholdDrop &&
      (now - lastHitTime[i] > debounceTime)
    ) {
      lastHitTime[i] = now;
      digitalWrite(ledPin, !digitalRead(ledPin)); // Flash LED on any hit

      if (i < 3) {
        // --- FINGER HIT (Data Bit) ---
        
        // 1. Reset space streak because we hit a finger
        spaceHitCount = 0; 

        // 2. Mark bit
        fingerHit[i] = true;
        if (firstHitTime == 0) firstHitTime = now;

      } else {
        // --- SPACE HIT (Piezo 3) ---
        spaceHitCount++;

        // Check if this is the 3rd hit in a row
        if (spaceHitCount >= 3) {
            // === SEND COMMAND ===
            // Remove the spaces added by the previous 2 hits so it looks clean
            binarySentence.trim(); 
            
            Serial.println(binarySentence);
            
            // Reset everything
            binarySentence = "";
            spaceHitCount = 0;
            resetFingers();
            
            // Visual feedback (long flash)
            digitalWrite(ledPin, HIGH); delay(200); digitalWrite(ledPin, LOW);
            return; // Exit loop briefly
        } 
        else {
            // === STANDARD SPACE ===
            // Just append a space (for hits 1 and 2)
            if (binarySentence.length() > 0 && 
                binarySentence[binarySentence.length() - 1] != ' ') {
              binarySentence += " ";
            }
        }
      }
    }

    lastReading[i] = reading;
  }

  // --- NOTE: Removed the "check ALL fingers pressed" block here ---

  // --- finish binary group after letterWait ---
  if (firstHitTime != 0 && (now - firstHitTime > letterWait)) {
    // append bits in order
    for (int i = 0; i < 3; i++) {
      binarySentence += fingerHit[i] ? "1" : "0";
    }
    resetFingers();
  }

  delay(5);
}

void resetFingers() {
  for (int i = 0; i < 3; i++) fingerHit[i] = false;
  firstHitTime = 0;
}