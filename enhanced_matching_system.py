
import numpy as np
import sqlite3
import json
import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict
import threading
import time
processing_status = {}
# Neural network imports (you'll need to install these)
try:
    import tensorflow as tf
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    HAS_ML_LIBRARIES = True
except ImportError:
    HAS_ML_LIBRARIES = False
    print("Warning: TensorFlow/sklearn not installed. Using fallback methods.")

# ============================================================================
# DATA COLLECTION & STORAGE
# ============================================================================

def safe_numeric(value, default=5.0):
    """Safely convert any value to numeric with fallback"""
    try:
        if isinstance(value, str):
            return float(value)
        elif isinstance(value, (int, float)):
            return float(value)
        else:
            return default
    except (ValueError, TypeError):
        return default
    
class MatchingDataCollector:
    """Collects and stores user interaction data for neural network training"""
    
    def __init__(self):
        self.init_data_tables()
    
    def init_data_tables(self):
        """Initialize data collection tables"""
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        
        # User interaction events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                interaction_type TEXT NOT NULL,
                target_user_id INTEGER,
                context_data TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                outcome TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Social clustering data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS social_clusters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                cluster_snapshot TEXT NOT NULL,
                cluster_metrics TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Neural network training data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_vector TEXT NOT NULL,
                target_outcome REAL NOT NULL,
                interaction_context TEXT,
                user_pair TEXT,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Model performance tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_version TEXT NOT NULL,
                accuracy REAL,
                precision_score REAL,
                recall_score REAL,
                training_data_size INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✓ Data collection tables initialized")
    
    def record_interaction(self, user_id: int, interaction_type: str, 
                          target_user_id: int = None, context_data: Dict = None, 
                          outcome: str = None, session_id: str = None):
        """Record user interaction for neural network training"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_interactions 
                (user_id, interaction_type, target_user_id, context_data, outcome, session_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, interaction_type, target_user_id, 
                  json.dumps(context_data) if context_data else None, 
                  outcome, session_id))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print(f"Error recording interaction: {e}")
            return False
    
    def get_training_data(self, min_interactions: int = 100) -> Tuple[np.ndarray, np.ndarray]:
        """Extract training data for neural network"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            # Get interaction data with outcomes
            cursor.execute('''
                SELECT ui.user_id, ui.target_user_id, ui.interaction_type, 
                       ui.context_data, ui.outcome, up1.profile_data, up2.profile_data
                FROM user_interactions ui
                JOIN user_profiles up1 ON ui.user_id = up1.user_id
                LEFT JOIN user_profiles up2 ON ui.target_user_id = up2.user_id
                WHERE ui.outcome IS NOT NULL
                ORDER BY ui.timestamp DESC
                LIMIT ?
            ''', (min_interactions * 10,))
            
            interactions = cursor.fetchall()
            conn.close()
            
            if len(interactions) < min_interactions:
                print(f"Warning: Only {len(interactions)} interactions available, need {min_interactions}")
                return None, None
            
            # Convert to feature vectors and targets
            features = []
            targets = []
            
            for interaction in interactions:
                feature_vector = self._extract_features(interaction)
                target = self._extract_target(interaction[4])  # outcome
                
                if feature_vector is not None and target is not None:
                    features.append(feature_vector)
                    targets.append(target)
            
            if len(features) < min_interactions:
                return None, None
                
            return np.array(features), np.array(targets)
            
        except Exception as e:
            print(f"Error getting training data: {e}")
            return None, None
    
    def _extract_features(self, interaction: Tuple) -> Optional[List[float]]:
        """Extract feature vector from interaction data - FIXED to 21 features"""
        try:
            user_id, target_user_id, interaction_type, context_data, outcome, profile1, profile2 = interaction
            
            # Parse profiles
            profile1_data = json.loads(profile1) if profile1 else {}
            profile2_data = json.loads(profile2) if profile2 else {}
            context = json.loads(context_data) if context_data else {}
            
            # Create feature vector (standardized format)
            features = []
            
            # User 1 features (6 features)
            features.extend([
                float(profile1_data.get('age', 25)) / 100.0,
                float(profile1_data.get('social_energy', 5)) / 10.0,
                float(profile1_data.get('decision_making', 5)) / 10.0,
                float(profile1_data.get('communication_depth', 5)) / 10.0,
                float(profile1_data.get('personal_growth', 5)) / 10.0,
                float(profile1_data.get('social_satisfaction', 5)) / 10.0,
            ])
            
            # User 2 features (6 features)
            if profile2_data:
                features.extend([
                    float(profile2_data.get('age', 25)) / 100.0,
                    float(profile2_data.get('social_energy', 5)) / 10.0,
                    float(profile2_data.get('decision_making', 5)) / 10.0,
                    float(profile2_data.get('communication_depth', 5)) / 10.0,
                    float(profile2_data.get('personal_growth', 5)) / 10.0,
                    float(profile2_data.get('social_satisfaction', 5)) / 10.0,
                ])
                
                # Compatibility differences (4 features) 
                features.append(abs(float(profile1_data.get('social_energy', 5)) - 
                                float(profile2_data.get('social_energy', 5))) / 10.0)
                features.append(abs(float(profile1_data.get('decision_making', 5)) - 
                                float(profile2_data.get('decision_making', 5))) / 10.0)
                features.append(abs(float(profile1_data.get('communication_depth', 5)) - 
                                float(profile2_data.get('communication_depth', 5))) / 10.0)
                features.append(abs(float(profile1_data.get('personal_growth', 5)) - 
                                float(profile2_data.get('personal_growth', 5))) / 10.0)
            else:
                # Pad with zeros if no target user (10 features: 6 + 4)
                features.extend([0.0] * 10)
            
            # Interaction context features (5 features)
            features.extend([
                1.0 if interaction_type == 'profile_view' else 0.0,
                1.0 if interaction_type == 'contact_request' else 0.0,
                1.0 if interaction_type == 'email_response' else 0.0,
                float(context.get('time_spent', 0)) / 300.0,  # normalize to 5 minutes
                float(context.get('compatibility_score', 0)) / 100.0,
            ])
            
            # Total: 6 + 6 + 4 + 5 = 21 features
            assert len(features) == 21, f"Expected 21 features, got {len(features)}"
            return features
            
        except Exception as e:
            print(f"Error extracting features: {e}")
            return None
    
    def _extract_target(self, outcome: str) -> Optional[float]:
        """Convert outcome to numerical target"""
        outcome_mapping = {
            'positive': 1.0,
            'contact_accepted': 0.9,
            'email_yes': 0.8,
            'neutral': 0.5,
            'contact_declined': 0.2,
            'email_no': 0.1,
            'negative': 0.0,
            'blocked': 0.0
        }
        return outcome_mapping.get(outcome)

# ============================================================================
# NEURAL NETWORK PREDICTOR
# ============================================================================

class SocialPredictionNetwork:
    """Neural network for predicting social compatibility and outcomes"""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_size = 21  # Based on feature extraction
        self.data_collector = MatchingDataCollector()
        
    def build_model(self):
        """Build the neural network architecture"""
        if not HAS_ML_LIBRARIES:
            print("Warning: ML libraries not available, using fallback")
            return False
            
        try:
            self.model = tf.keras.Sequential([
                tf.keras.layers.Dense(128, activation='relu', input_shape=(self.feature_size,)),
                tf.keras.layers.Dropout(0.3),
                tf.keras.layers.Dense(64, activation='relu'),
                tf.keras.layers.Dropout(0.2),
                tf.keras.layers.Dense(32, activation='relu'),
                tf.keras.layers.Dense(16, activation='relu'),
                tf.keras.layers.Dense(1, activation='sigmoid')  # Output probability
            ])
            
            self.model.compile(
                optimizer='adam',
                loss='binary_crossentropy',
                metrics=['accuracy', 'precision', 'recall']
            )
            
            return True
            
        except Exception as e:
            print(f"Error building model: {e}")
            return False
    
    def train_model(self, min_data_points: int = 200):
        """Train the neural network on collected data"""
        if not HAS_ML_LIBRARIES:
            return False
            
        try:
            # Get training data
            X, y = self.data_collector.get_training_data(min_data_points)
            
            if X is None or len(X) < min_data_points:
                print(f"Insufficient training data: {len(X) if X is not None else 0} samples")
                return False
            
            print(f"Training with {len(X)} samples")
            
            # Preprocess data
            X_scaled = self.scaler.fit_transform(X)
            
            # Split data
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )
            
            # Build model if not exists
            if self.model is None:
                if not self.build_model():
                    return False
            
            # Train model
            history = self.model.fit(
                X_train, y_train,
                epochs=50,
                batch_size=32,
                validation_data=(X_test, y_test),
                verbose=1
            )
            
            # Evaluate model
            test_loss, test_accuracy, test_precision, test_recall = self.model.evaluate(X_test, y_test, verbose=0)
            
            # Store performance metrics
            self._save_performance_metrics(test_accuracy, test_precision, test_recall, len(X))
            
            self.is_trained = True
            print(f"✓ Model trained successfully - Accuracy: {test_accuracy:.3f}")
            return True
            
        except Exception as e:
            print(f"Error training model: {e}")
            return False
    
    def predict_compatibility(self, user1_profile: Dict, user2_profile: Dict, 
                            context: Dict = None) -> float:
        """Predict compatibility between two users"""
        if not self.is_trained or not HAS_ML_LIBRARIES:
            return self._fallback_prediction(user1_profile, user2_profile)
        
        try:
            # Create feature vector
            interaction_data = (
                None, None, 'prediction', 
                json.dumps(context) if context else None, 
                None, json.dumps(user1_profile), json.dumps(user2_profile)
            )
            
            features = self.data_collector._extract_features(interaction_data)
            
            if features is None:
                return self._fallback_prediction(user1_profile, user2_profile)
            
            # Scale features
            features_scaled = self.scaler.transform([features])
            
            # Predict
            prediction = self.model.predict(features_scaled, verbose=0)[0][0]
            
            return float(prediction)
            
        except Exception as e:
            print(f"Error in neural prediction: {e}")
            return self._fallback_prediction(user1_profile, user2_profile)
    
    def _fallback_prediction(self, user1_profile: Dict, user2_profile: Dict) -> float:
        """Fallback prediction when neural network is not available"""
        
        # Helper function to safely convert to numeric
        def safe_numeric(value, default=25):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        # Simple compatibility calculation with safe conversion
        age_diff = abs(safe_numeric(user1_profile.get('age', 25)) - safe_numeric(user2_profile.get('age', 25)))
        age_score = max(0, 1 - age_diff / 20)
        
        social_diff = abs(safe_numeric(user1_profile.get('social_energy', 5)) - safe_numeric(user2_profile.get('social_energy', 5)))
        social_score = max(0, 1 - social_diff / 10)
        
        values_diff = abs(safe_numeric(user1_profile.get('personal_growth', 5)) - safe_numeric(user2_profile.get('personal_growth', 5)))
        values_score = max(0, 1 - values_diff / 10)
        
        return (age_score + social_score + values_score) / 3
    def _save_performance_metrics(self, accuracy: float, precision: float, 
                                 recall: float, data_size: int):
        """Save model performance metrics"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            model_version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            cursor.execute('''
                INSERT INTO model_performance 
                (model_version, accuracy, precision_score, recall_score, training_data_size)
                VALUES (?, ?, ?, ?, ?)
            ''', (model_version, accuracy, precision, recall, data_size))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error saving performance metrics: {e}")

# ============================================================================
# AGENT-BASED SOCIAL SIMULATION
# ============================================================================

@dataclass
class SocialAgent:
    """Represents a user as an agent in the social simulation"""
    user_id: int
    profile: Dict[str, Any]
    position: Tuple[float, float]  # Position in social space
    connections: List[int]
    satisfaction: float
    social_energy: float
    compatibility_threshold: float

class SocialSimulation:
    """Agent-based social simulation inspired by Schelling's model"""
    
    def __init__(self, width: int = 100, height: int = 100, user_id: int = None):
        self.width = width
        self.height = height
        self.user_id = user_id  # Add this line
        self.agents: Dict[int, SocialAgent] = {}
        self.grid = np.zeros((height, width))
        self.neural_predictor = SocialPredictionNetwork()
        self.simulation_steps = 0
        # Add real-time update storage
        self.simulation_updates = []
        
    def add_agent(self, user_id: int, profile: Dict[str, Any]):
        """Add a user as an agent to the simulation"""
        
        # Helper function to safely convert to float
        def safe_float(value, default=5.0):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        # Position based on personality characteristics - with safe conversion
        social_energy = safe_float(profile.get('social_energy', 5))
        personal_growth = safe_float(profile.get('personal_growth', 5))
        social_satisfaction = safe_float(profile.get('social_satisfaction', 5))
        
        social_x = (social_energy / 10.0) * self.width
        values_y = (personal_growth / 10.0) * self.height
        
        # Add some randomness
        x = max(0, min(self.width - 1, int(social_x + random.uniform(-10, 10))))
        y = max(0, min(self.height - 1, int(values_y + random.uniform(-10, 10))))
        
        agent = SocialAgent(
            user_id=user_id,
            profile=profile,
            position=(x, y),
            connections=[],
            satisfaction=social_satisfaction / 10.0,
            social_energy=social_energy / 10.0,
            compatibility_threshold=0.6  # Adjust based on user preferences
        )
        
        self.agents[user_id] = agent
        self.grid[y, x] = user_id
        # Store initial position for visualization
        self.broadcast_agent_update(user_id, x, y, agent.satisfaction)
    
    def find_neighbors(self, agent: SocialAgent, radius: int = 15) -> List[SocialAgent]:
        """Find neighboring agents within radius"""
        neighbors = []
        x, y = agent.position
        
        for other_id, other_agent in self.agents.items():
            if other_id == agent.user_id:
                continue
                
            ox, oy = other_agent.position
            distance = math.sqrt((x - ox)**2 + (y - oy)**2)
            
            if distance <= radius:
                neighbors.append(other_agent)
        
        return neighbors
    
    def calculate_agent_satisfaction(self, agent: SocialAgent) -> float:
        """Calculate agent satisfaction based on local neighborhood"""
        neighbors = self.find_neighbors(agent, radius=20)
        
        if not neighbors:
            return 0.3  # Low satisfaction when isolated
        
        compatibility_scores = []
        for neighbor in neighbors:
            # Use neural network prediction if available
            compatibility = self.neural_predictor.predict_compatibility(
                agent.profile, neighbor.profile
            )
            compatibility_scores.append(compatibility)
        
        # Satisfaction based on average neighborhood compatibility
        avg_compatibility = sum(compatibility_scores) / len(compatibility_scores)
        
        # Factor in social energy preferences
        crowd_factor = len(neighbors) / 20.0  # Normalize by max neighbors
        if agent.social_energy > 0.7:  # Extroverted
            satisfaction = avg_compatibility * (0.7 + 0.3 * crowd_factor)
        else:  # Introverted
            satisfaction = avg_compatibility * (1.0 - 0.2 * crowd_factor)
        
        return min(1.0, satisfaction)
    
    def broadcast_agent_update(self, agent_id: int, x: float, y: float, satisfaction: float):
        """Store agent update for real-time visualization"""
        if self.user_id and self.user_id in processing_status:  # Use self.user_id
            if 'agents_positions' not in processing_status[self.user_id]:
                processing_status[self.user_id]['agents_positions'] = {}
            
            processing_status[self.user_id]['agents_positions'][agent_id] = {
                'x': float(x),
                'y': float(y),
                'satisfaction': float(satisfaction),
                'timestamp': time.time()
            }
    
    def move_agent(self, agent: SocialAgent):
        """Move agent to improve satisfaction (Schelling-style)"""
        current_satisfaction = self.calculate_agent_satisfaction(agent)
        
        # Only move if satisfaction is below threshold
        if current_satisfaction >= agent.compatibility_threshold:
            agent.satisfaction = current_satisfaction
            return False
        
        # Try random nearby positions
        best_position = agent.position
        best_satisfaction = current_satisfaction
        
        x, y = agent.position
        for _ in range(10):  # Try 10 random moves
            new_x = max(0, min(self.width - 1, x + random.randint(-15, 15)))
            new_y = max(0, min(self.height - 1, y + random.randint(-15, 15)))
            
            # Temporarily move agent
            old_pos = agent.position
            agent.position = (new_x, new_y)
            
            satisfaction = self.calculate_agent_satisfaction(agent)
            
            if satisfaction > best_satisfaction:
                best_position = (new_x, new_y)
                best_satisfaction = satisfaction
            
            # Restore position for next test
            agent.position = old_pos
        
        # Make the best move
        if best_position != agent.position:
            old_x, old_y = agent.position
            self.grid[old_y, old_x] = 0
            
            agent.position = best_position
            agent.satisfaction = best_satisfaction
            
            new_x, new_y = best_position
            self.grid[new_y, new_x] = agent.user_id
            # Broadcast the move in real-time
            self.broadcast_agent_update(agent.user_id, new_x, new_y, best_satisfaction)
            return True
        
        return False
    
    def run_simulation(self, steps: int = 50) -> Dict[str, Any]:
        """Run simulation with real-time updates"""
        moves_per_step = []
        satisfaction_history = []
        
        print(f"Starting real-time simulation with {len(self.agents)} agents")
        
        for step in range(steps):
            moves_this_step = 0
            total_satisfaction = 0
            
            # Update global status
            if self.user_id and self.user_id in processing_status:
                processing_status[self.user_id].update({
                    'simulation_step': step + 1,
                    'total_steps': steps,
                    'status': 'simulating'
                })
            
            # Randomly shuffle agents
            agent_ids = list(self.agents.keys())
            random.shuffle(agent_ids)
            
            for agent_id in agent_ids:
                agent = self.agents[agent_id]
                if self.move_agent(agent):
                    moves_this_step += 1
                total_satisfaction += agent.satisfaction
            
            avg_satisfaction = total_satisfaction / len(self.agents)
            moves_per_step.append(moves_this_step)
            satisfaction_history.append(avg_satisfaction)
            
            # Broadcast step completion
            if self.user_id:
                processing_status[self.user_id].update({
                    'agents_moved': moves_this_step,
                    'avg_satisfaction': int(avg_satisfaction * 100),
                    'simulation_progress': ((step + 1) / steps) * 100
                })
            
            print(f"Step {step + 1}: {moves_this_step} moves, {avg_satisfaction:.3f} satisfaction")
            
            # Sleep to make visualization visible
            time.sleep(0.3)  # 300ms between steps
            
            # Early stopping if converged
            if moves_this_step == 0:
                print(f"Simulation converged at step {step + 1}")
                break
        
        self.simulation_steps = step + 1
        
        return {
            'total_steps': self.simulation_steps,
            'final_avg_satisfaction': satisfaction_history[-1] if satisfaction_history else 0,
            'moves_per_step': moves_per_step,
            'satisfaction_history': satisfaction_history
        }
    
    def get_clusters_for_user(self, target_user_id: int, cluster_size: int = 10) -> List[int]:
        """Get the cluster of users most similar to target user"""
        if target_user_id not in self.agents:
            return []
        
        target_agent = self.agents[target_user_id]
        
        # Find agents in proximity after simulation
        neighbors = self.find_neighbors(target_agent, radius=25)
        
        # Sort by compatibility using neural network
        neighbor_scores = []
        for neighbor in neighbors:
            compatibility = self.neural_predictor.predict_compatibility(
                target_agent.profile, neighbor.profile
            )
            neighbor_scores.append((neighbor.user_id, compatibility))
        
        # Sort by compatibility score
        neighbor_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Return top matches
        return [user_id for user_id, score in neighbor_scores[:cluster_size]]

# ============================================================================
# ENHANCED MATCHING SYSTEM
# ============================================================================

class EnhancedMatchingSystem:
    """Enhanced matching system using agent-based modeling + neural networks"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.user_auth = None  # Will be injected
        self.data_collector = MatchingDataCollector()
        self.neural_predictor = SocialPredictionNetwork()
        self.simulation = SocialSimulation()
        self.min_neural_data = 10  # Minimum interactions for neural network
        self.processing_status = {} 
        # Try to load existing model
        self._initialize_neural_network()
    
    def set_user_auth(self, user_auth_system):
        """Inject user authentication system"""
        self.user_auth = user_auth_system
    
    def _initialize_neural_network(self):
        """Initialize and train neural network if enough data exists"""
        try:
            # Check if we have enough data for neural training
            X, y = self.data_collector.get_training_data(self.min_neural_data)
            
            if X is not None and len(X) >= self.min_neural_data:
                print(f"Training neural network with {len(X)} samples...")
                success = self.neural_predictor.train_model(self.min_neural_data)
                if success:
                    print("✓ Neural network initialized and trained")
                else:
                    print("⚠ Neural network training failed, using fallback")
            else:
                print(f"⚠ Insufficient data for neural training ({len(X) if X is not None else 0}/{self.min_neural_data})")
                
        except Exception as e:
            print(f"Error initializing neural network: {e}")
    
    def record_user_interaction(self, user_id: int, interaction_type: str, 
                              target_user_id: int = None, context: Dict = None, 
                              outcome: str = None):
        """Record user interaction for learning"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user_id}"
        
        self.data_collector.record_interaction(
            user_id, interaction_type, target_user_id, context, outcome, session_id
        )
        
        # Retrain neural network periodically
        self._maybe_retrain_network()
    
    def _maybe_retrain_network(self):
        """Retrain neural network if enough new data accumulated"""
        try:
            # Check total interaction count
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM user_interactions WHERE outcome IS NOT NULL')
            total_interactions = cursor.fetchone()[0]
            
            # Get last training time
            cursor.execute('SELECT MAX(created_at) FROM model_performance')
            last_training = cursor.fetchone()[0]
            
            conn.close()
            
            # Retrain if significant new data or been a while
            should_retrain = (
                total_interactions >= self.min_neural_data and 
                (not last_training or 
                 (datetime.now() - datetime.fromisoformat(last_training)).days >= 7)
            )
            
            if should_retrain:
                print("Retraining neural network with new data...")
                threading.Thread(target=self.neural_predictor.train_model, 
                               args=(self.min_neural_data,)).start()
                
        except Exception as e:
            print(f"Error checking retrain conditions: {e}")
    
    def is_user_blocked(self, user_id: int, potential_match: Dict[str, Any]) -> bool:
        """Check if a potential match is blocked (unchanged from original)"""
        if not self.user_auth:
            return False
            
        blocked = self.user_auth.get_blocked_users(user_id)
        
        # Check email, phone, and name matches
        if potential_match['email'] in blocked['emails']:
            return True
        if potential_match.get('phone') and potential_match['phone'] in blocked['phones']:
            return True
        
        user_name = f"{potential_match['first_name']} {potential_match['last_name']}".lower()
        for blocked_name in blocked['names']:
            if blocked_name and blocked_name.lower() in user_name:
                return True
        
        return False
    
    def check_gender_compatibility(self, user1_profile: Dict, user2_profile: Dict) -> bool:
        """Check if users meet each other's gender preferences (unchanged)"""
        user1_gender = user1_profile.get('gender', '')
        user2_gender = user2_profile.get('gender', '')
        user1_preference = user1_profile.get('gender_preference', 'all')
        user2_preference = user2_profile.get('gender_preference', 'all')
        
        # Check mutual compatibility
        user1_compatible = (user1_preference == 'all' or 
                           (user1_preference == 'women' and user2_gender == 'woman') or
                           (user1_preference == 'men' and user2_gender == 'man') or
                           (user1_preference == 'non_binary' and user2_gender == 'non_binary'))
        
        user2_compatible = (user2_preference == 'all' or 
                           (user2_preference == 'women' and user1_gender == 'woman') or
                           (user2_preference == 'men' and user1_gender == 'man') or
                           (user2_preference == 'non_binary' and user1_gender == 'non_binary'))
        
        return user1_compatible and user2_compatible
    
    def run_matching(self, user_id: int) -> List[Dict[str, Any]]:
        """Run enhanced matching with real-time agent visualization"""
        print(f"\n=== Running Real-Time Enhanced Matching for {user_id} ===")
        
        # Initialize processing status for real-time updates
        processing_status[user_id] = {
            'status': 'initializing',
            'progress': 0,
            'simulation_step': 0,
            'agents_moved': 0,
            'avg_satisfaction': 30,
            'agents_positions': {},
            'phase': 'data_collection'
        }
        
        # Get user data
        current_user_profile = self.user_auth.get_user_profile(user_id)
        current_user_info = self.user_auth.get_user_info(user_id)
        
        if not current_user_profile or not current_user_info:
            print("ERROR: Current user profile not found!")
            return []
        
        # Update status
        processing_status[user_id].update({
            'phase': 'filtering_users',
            'progress': 10
        })
        
        # Get and filter users
        all_users = self.user_auth.get_all_users_for_matching(user_id)
        valid_users = []
        
        for potential_match in all_users:
            if self.is_user_blocked(user_id, potential_match):
                continue
            if not self.check_gender_compatibility(current_user_profile, potential_match['profile']):
                continue
            valid_users.append(potential_match)
        
        print(f"Found {len(valid_users)} valid users after filtering")
        
        # Update status
        processing_status[user_id].update({
            'phase': 'initializing_simulation',
            'progress': 20
        })
        
        # Initialize simulation with user_id for real-time updates
        self.simulation = SocialSimulation(width=800, height=500, user_id=user_id)
        
        # Add current user
        self.simulation.add_agent(user_id, current_user_profile)
        
        # Add other users
        for user in valid_users[:20]:  # Limit for performance
            self.simulation.add_agent(user['user_id'], user['profile'])
        
        # Store agent metadata for frontend
        agents_metadata = {}
        
        # User agent metadata
        agents_metadata[user_id] = {
            'id': user_id,
            'type': 'user',
            'name': 'You',
            'email': current_user_info['email'],
            'compatibility_level': 'user'
        }
        
        # Other agents metadata
        for user in valid_users[:20]:
            # Calculate compatibility for visualization
            compatibility = self.simulation.neural_predictor.predict_compatibility(
                current_user_profile, user['profile']
            )
            
            if compatibility > 0.75:
                compat_level = 'high-compat'
            elif compatibility > 0.45:
                compat_level = 'medium-compat'
            else:
                compat_level = 'low-compat'
            
            agents_metadata[user['user_id']] = {
                'id': user['user_id'],
                'type': compat_level,
                'name': user['first_name'],
                'email': user['email'],
                'compatibility_score': compatibility,
                'compatibility_level': compat_level
            }
        
        processing_status[user_id]['agents_metadata'] = agents_metadata
        
        # Update status
        processing_status[user_id].update({
            'phase': 'running_simulation',
            'progress': 30
        })
        
        # Run the real simulation with real-time updates
        print("Running agent-based social simulation with real-time updates...")
        simulation_results = self.simulation.run_simulation(steps=50)
        
        print(f"✓ Real-time simulation completed in {simulation_results['total_steps']} steps")
        
        # Update status
        processing_status[user_id].update({
            'phase': 'generating_matches',
            'progress': 80
        })
        
        # Generate matches based on final simulation state
        clustered_user_ids = self.simulation.get_clusters_for_user(user_id, cluster_size=15)
        matches = []
        
        for match_user_id in clustered_user_ids:
            match_user = next((u for u in valid_users if u['user_id'] == match_user_id), None)
            if not match_user:
                continue
            
            # Get neural network prediction
            neural_compatibility = self.simulation.neural_predictor.predict_compatibility(
                current_user_profile, match_user['profile']
            )
            
            # Calculate detailed scores
            detailed_scores = self._calculate_detailed_scores(
                current_user_profile, match_user['profile'], neural_compatibility
            )
            
            # Final agent position from simulation
            final_agent = self.simulation.agents.get(match_user_id)
            final_satisfaction = final_agent.satisfaction if final_agent else 0.5
            
            overall_score = (neural_compatibility * 0.6 + final_satisfaction * 0.4) * 100
            
            match_result = {
                'matched_user_id': match_user['user_id'],
                'matched_user_name': match_user['first_name'],
                'matched_user_email': match_user['email'],
                'matched_user_phone': match_user.get('phone', ''),
                'compatibility_score': round(overall_score),
                'neural_score': round(neural_compatibility * 100),
                'simulation_satisfaction': round(final_satisfaction * 100),
                'personality_score': round(detailed_scores['personality_score']),
                'values_score': round(detailed_scores['values_score']),
                'lifestyle_score': round(detailed_scores['lifestyle_score']),
                'emotional_score': round(detailed_scores['emotional_score']),
                'social_score': round(detailed_scores['social_score']),
                'communication_score': round(detailed_scores['communication_score']),
                'location_score': 85,
                'overall_score': round(overall_score),
                'compatibility_analysis': self._generate_match_analysis(
                    current_user_profile, match_user['profile'], neural_compatibility, 
                    detailed_scores, simulation_results
                ),
                'distance_miles': 0,
                'final_position': final_agent.position if final_agent else (0, 0)
            }
            
            matches.append(match_result)
        
        # Sort and save matches
        matches.sort(key=lambda x: x['overall_score'], reverse=True)
        matches = [m for m in matches if m['overall_score'] >= 60]
        
        if self.user_auth:
            self.user_auth.save_user_matches(user_id, matches)
        
        # Final status update
        processing_status[user_id] = {
            'status': 'completed',
            'progress': 100,
            'matches': matches,
            'total_matches': len(matches),
            'simulation_completed': True
        }
        
        print(f"✓ Real-time matching completed - found {len(matches)} matches")
        return matches
    
    def _calculate_detailed_scores(self, user1_profile: Dict, user2_profile: Dict, 
                             neural_score: float) -> Dict[str, float]:
        """Calculate detailed compatibility scores (traditional method for backup)"""
        
        # Helper function to safely convert to float
        def safe_float(value, default=5.0):
            try:
                if isinstance(value, str):
                    return float(value)
                elif isinstance(value, (int, float)):
                    return float(value)
                else:
                    return default
            except (ValueError, TypeError):
                return default
        
        scores = {}
        
        # Personality compatibility
        personality_scores = []
        decision_diff = abs(safe_float(user1_profile.get('decision_making', 5)) - 
                        safe_float(user2_profile.get('decision_making', 5)))
        personality_scores.append(max(0, 100 - (decision_diff * 8)))
        
        social_diff = abs(safe_float(user1_profile.get('social_energy', 5)) - 
                        safe_float(user2_profile.get('social_energy', 5)))
        personality_scores.append(max(0, 100 - (social_diff * 12)))
        
        comm_diff = abs(safe_float(user1_profile.get('communication_depth', 5)) - 
                    safe_float(user2_profile.get('communication_depth', 5)))
        personality_scores.append(max(0, 100 - (comm_diff * 15)))
        
        scores['personality_score'] = sum(personality_scores) / len(personality_scores)
        
        # Values compatibility
        values_scores = []
        growth_diff = abs(safe_float(user1_profile.get('personal_growth', 5)) - 
                        safe_float(user2_profile.get('personal_growth', 5)))
        values_scores.append(max(0, 100 - (growth_diff * 10)))
        
        success_diff = abs(safe_float(user1_profile.get('success_definition', 5)) - 
                        safe_float(user2_profile.get('success_definition', 5)))
        values_scores.append(max(0, 100 - (success_diff * 12)))
        
        scores['values_score'] = sum(values_scores) / len(values_scores)
        
        # Lifestyle compatibility
        lifestyle_scores = []
        energy_diff = abs(safe_float(user1_profile.get('energy_patterns', 5)) - 
                        safe_float(user2_profile.get('energy_patterns', 5)))
        lifestyle_scores.append(max(0, 100 - (energy_diff * 15)))
        
        activity_diff = abs(safe_float(user1_profile.get('activity_investment', 5)) - 
                        safe_float(user2_profile.get('activity_investment', 5)))
        lifestyle_scores.append(max(0, 100 - (activity_diff * 7)))
        
        scores['lifestyle_score'] = sum(lifestyle_scores) / len(lifestyle_scores)
        
        # Emotional and social scores (simplified)
        scores['emotional_score'] = 75 + (neural_score - 0.5) * 50  # Influenced by neural prediction
        scores['social_score'] = 75 + (neural_score - 0.5) * 50
        scores['communication_score'] = 75 + (neural_score - 0.5) * 50
        
        # Traditional overall score
        scores['traditional_score'] = (
            scores['personality_score'] * 0.25 +
            scores['values_score'] * 0.20 +
            scores['lifestyle_score'] * 0.15 +
            scores['emotional_score'] * 0.20 +
            scores['social_score'] * 0.10 +
            scores['communication_score'] * 0.10
        ) / 100
        
        return scores
    
    def _generate_match_analysis(self, user1_profile: Dict, user2_profile: Dict, 
                           neural_score: float, detailed_scores: Dict, 
                           simulation_results: Dict) -> str:
        """Generate comprehensive match analysis"""
        
        # Determine analysis style based on neural network confidence
        try:
            training_data = self.data_collector.get_training_data(10)
            if training_data[0] is not None and len(training_data[0]) > 0:
                data_weight = min(1.0, len(training_data[0]) / 1000)
            else:
                data_weight = 0.0
        except Exception as e:
            print(f"Error getting training data weight: {e}")
            data_weight = 0.0
        
        if data_weight > 0.7:
            # High confidence neural analysis
            analyses = [
                f"Our AI predicts a {neural_score*100:.0f}% compatibility based on learned patterns from successful connections. This match was identified through advanced social simulation where you naturally clustered together.",
                f"The neural network analysis suggests you share complementary interaction styles and values. After {simulation_results['total_steps']} simulation steps, you ended up in the same social cluster with {simulation_results['final_avg_satisfaction']:.1f} satisfaction.",
                f"Based on thousands of successful friendship patterns, our AI identifies strong potential for meaningful connection. Your profiles suggest natural alignment in social preferences and communication styles.",
                f"Advanced pattern recognition indicates you both have compatible approaches to friendship building. The social simulation shows you'd likely enjoy similar environments and interaction styles."
            ]
        else:
            # Traditional analysis with some AI insights - FIX: Use safe_numeric here too
            social_energy_diff = abs(safe_numeric(user1_profile.get('social_energy', 5)) - safe_numeric(user2_profile.get('social_energy', 5)))
            personality_desc = "complementary" if social_energy_diff <= 3 else "different but potentially enriching"
            
            analyses = [
                f"Your {personality_desc} personality traits and shared values around personal growth suggest great potential for meaningful friendship. Social simulation indicates natural compatibility.",
                f"Both of you value authentic connections and have compatible approaches to life's challenges. The AI-assisted analysis shows strong alignment in friendship expectations.",
                f"Your different strengths could complement each other beautifully - creating a balanced and supportive friendship dynamic based on simulation modeling.",
                f"Similar lifestyle rhythms and social preferences suggest you'd enjoy spending time together, with AI prediction supporting long-term compatibility."
            ]
        
        return random.choice(analyses)
    def _save_cluster_data(self, user_id: int, cluster_user_ids: List[int], 
                          simulation_results: Dict):
        """Save clustering results for analysis"""
        try:
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            
            cluster_data = {
                'user_id': user_id,
                'cluster_members': cluster_user_ids,
                'simulation_results': simulation_results,
                'agent_position': self.simulation.agents[user_id].position,
                'agent_satisfaction': self.simulation.agents[user_id].satisfaction
            }
            
            metrics = {
                'cluster_size': len(cluster_user_ids),
                'simulation_steps': simulation_results['total_steps'],
                'final_satisfaction': simulation_results['final_avg_satisfaction']
            }
            
            cursor.execute('''
                INSERT INTO social_clusters (user_id, cluster_snapshot, cluster_metrics)
                VALUES (?, ?, ?)
            ''', (user_id, json.dumps(cluster_data), json.dumps(metrics)))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error saving cluster data: {e}")

# ============================================================================
# INTERACTION TRACKING INTEGRATION
# ============================================================================

class InteractionTracker:
    """Tracks user interactions for continuous learning"""
    
    def __init__(self, matching_system: EnhancedMatchingSystem):
        self.matching_system = matching_system
    
    def track_profile_view(self, user_id: int, viewed_user_id: int, time_spent: float):
        """Track when user views another user's profile"""
        self.matching_system.record_user_interaction(
            user_id, 'profile_view', viewed_user_id,
            context={'time_spent': time_spent},
            outcome='neutral'
        )
    
    def track_contact_request(self, user_id: int, requested_user_id: int, 
                            compatibility_score: float):
        """Track contact request (positive signal)"""
        self.matching_system.record_user_interaction(
            user_id, 'contact_request', requested_user_id,
            context={'compatibility_score': compatibility_score},
            outcome='positive'
        )
    
    def track_contact_response(self, user_id: int, requester_id: int, accepted: bool):
        """Track contact request response"""
        outcome = 'contact_accepted' if accepted else 'contact_declined'
        self.matching_system.record_user_interaction(
            user_id, 'contact_response', requester_id,
            outcome=outcome
        )
    
    def track_email_response(self, user_id: int, other_user_id: int, would_meet_again: bool):
        """Track follow-up email response"""
        outcome = 'email_yes' if would_meet_again else 'email_no'
        self.matching_system.record_user_interaction(
            user_id, 'email_response', other_user_id,
            outcome=outcome
        )
    
    def track_user_blocking(self, user_id: int, blocked_user_id: int):
        """Track when user blocks someone (strong negative signal)"""
        self.matching_system.record_user_interaction(
            user_id, 'user_blocked', blocked_user_id,
            outcome='blocked'
        )

# ============================================================================
# INTEGRATION WITH EXISTING SYSTEM
# ============================================================================

def integrate_enhanced_matching(app, user_auth_system, api_key: str = None):
    """Integration function to replace existing matching system"""
    
    # Initialize enhanced matching system
    enhanced_matcher = EnhancedMatchingSystem(api_key)
    enhanced_matcher.set_user_auth(user_auth_system)
    
    # Initialize interaction tracker
    interaction_tracker = InteractionTracker(enhanced_matcher)
    
    # Replace the global matching system
    return enhanced_matcher, interaction_tracker

# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

def test_enhanced_matching():
    """Test function for the enhanced matching system"""
    
    # Create test profiles
    test_profiles = [
        {
            'user_id': 1,
            'age': 28,
            'social_energy': 7,
            'decision_making': 6,
            'communication_depth': 8,
            'personal_growth': 9,
            'social_satisfaction': 5
        },
        {
            'user_id': 2,
            'age': 26,
            'social_energy': 8,
            'decision_making': 7,
            'communication_depth': 9,
            'personal_growth': 8,
            'social_satisfaction': 6
        },
        {
            'user_id': 3,
            'age': 30,
            'social_energy': 4,
            'decision_making': 5,
            'communication_depth': 6,
            'personal_growth': 7,
            'social_satisfaction': 4
        }
    ]
    
    # Initialize system
    enhanced_matcher = EnhancedMatchingSystem()
    tracker = InteractionTracker(enhanced_matcher)
    
    # Add test interactions
    tracker.track_profile_view(1, 2, 45.0)
    tracker.track_contact_request(1, 2, 85.0)
    tracker.track_contact_response(2, 1, True)
    tracker.track_email_response(1, 2, True)
    
    print("✓ Enhanced matching system test completed")

if __name__ == "__main__":
    test_enhanced_matching()