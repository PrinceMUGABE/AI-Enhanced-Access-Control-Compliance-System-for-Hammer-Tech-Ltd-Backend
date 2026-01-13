# assistanceApp/free_ai_service.py
import json
from typing import Dict, List, Optional
from django.conf import settings
import time
import random
from sentence_transformers import SentenceTransformer, util
import torch

from .models import FAQ, AssistanceChat, AssistanceMessage, AIResponseLog


class FreeAIService:
    """FREE AI service using local models - no API key needed!"""
    
    def __init__(self):
        print("🚀 Initializing FREE AI Service...")
        
        try:
            # Load a small, fast embedding model for FAQ matching
            print("📥 Loading embedding model...")
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            print("✅ Embedding model loaded!")
            
            # Load FAQ embeddings
            self.faq_embeddings = None
            self.faq_data = []
            self._load_faq_embeddings()
            
        except Exception as e:
            print(f"⚠️ Could not load models: {e}")
            print("📝 Using rule-based fallback system")
            self.embedding_model = None
    
    def _load_faq_embeddings(self):
        """Load and embed all FAQs"""
        try:
            faqs = FAQ.objects.filter(is_active=True)
            self.faq_data = []
            faq_texts = []
            
            for faq in faqs:
                self.faq_data.append({
                    'id': faq.id,
                    'question': faq.question,
                    'answer': faq.answer,
                    'keywords': faq.keywords
                })
                # Combine question and keywords for better matching
                faq_texts.append(f"{faq.question} {faq.keywords}")
            
            if faq_texts and self.embedding_model:
                self.faq_embeddings = self.embedding_model.encode(faq_texts, convert_to_tensor=True)
                print(f"✅ Loaded embeddings for {len(faq_texts)} FAQs")
            else:
                print("ℹ️ No FAQs found or model not loaded")
                
        except Exception as e:
            print(f"❌ Error loading FAQ embeddings: {e}")
    
    def generate_response(self, user_query: str, chat_context: List[Dict] = None) -> Dict:
        """
        Generate AI response using FREE local models
        """
        start_time = time.time()
        
        try:
            # 1. Try FAQ matching first
            faq_match = self._match_faq(user_query)
            if faq_match and faq_match['confidence'] > 0.6:
                print(f"✅ FAQ match found (confidence: {faq_match['confidence']:.2f})")
                return {
                    'response': faq_match['answer'],
                    'confidence': faq_match['confidence'],
                    'faq_id': faq_match['id'],
                    'source': 'faq'
                }
            
            # 2. Use rule-based responses for common questions
            rule_response = self._rule_based_response(user_query)
            if rule_response:
                print(f"✅ Rule-based response found")
                return {
                    'response': rule_response['answer'],
                    'confidence': rule_response['confidence'],
                    'faq_id': None,
                    'source': 'rules'
                }
            
            # 3. Generate template-based response
            response = self._template_response(user_query)
            response_time = time.time() - start_time
            
            print(f"✅ Generated response in {response_time:.2f}s")
            
            return {
                'response': response,
                'confidence': 0.7,
                'faq_id': None,
                'source': 'template',
                'response_time': response_time
            }
            
        except Exception as e:
            print(f"❌ AI service error: {str(e)}")
            return self._fallback_response(user_query)
    
    def _match_faq(self, user_query: str) -> Optional[Dict]:
        """Match user query with FAQs using embeddings"""
        try:
            if not self.embedding_model or not self.faq_embeddings:
                return self._simple_faq_match(user_query)
            
            # Encode user query
            query_embedding = self.embedding_model.encode(user_query, convert_to_tensor=True)
            
            # Calculate similarity with all FAQs
            similarities = util.cos_sim(query_embedding, self.faq_embeddings)[0]
            
            # Find best match
            best_score, best_idx = torch.max(similarities, dim=0)
            best_score = best_score.item()
            
            if best_score > 0.4:  # Good match threshold
                faq = self.faq_data[best_idx]
                
                # Update FAQ counter
                try:
                    faq_obj = FAQ.objects.get(id=faq['id'])
                    faq_obj.times_asked += 1
                    faq_obj.save()
                except:
                    pass
                
                return {
                    'id': faq['id'],
                    'answer': faq['answer'],
                    'confidence': best_score
                }
            
        except Exception as e:
            print(f"FAQ matching error: {e}")
        
        return None
    
    def _simple_faq_match(self, user_query: str) -> Optional[Dict]:
        """Simple keyword-based FAQ matching"""
        try:
            user_query_lower = user_query.lower()
            faqs = FAQ.objects.filter(is_active=True)
            
            for faq in faqs:
                # Check keywords
                keywords = [k.strip().lower() for k in faq.keywords.split(',')]
                for keyword in keywords:
                    if keyword and keyword in user_query_lower:
                        faq.times_asked += 1
                        faq.save()
                        return {
                            'id': faq.id,
                            'answer': faq.answer,
                            'confidence': 0.8
                        }
                
                # Check question words
                question_words = set(faq.question.lower().split()[:10])
                query_words = set(user_query_lower.split())
                common_words = question_words.intersection(query_words)
                
                if len(common_words) >= 2:
                    faq.times_asked += 1
                    faq.save()
                    return {
                        'id': faq.id,
                        'answer': faq.answer,
                        'confidence': 0.6
                    }
            
        except Exception as e:
            print(f"Simple FAQ error: {e}")
        
        return None
    
    def _rule_based_response(self, user_query: str) -> Optional[Dict]:
        """Rule-based responses for common questions"""
        user_query_lower = user_query.lower()
        
        # Define rules for common questions
        rules = [
            {
                'keywords': ['hello', 'hi', 'hey', 'greetings'],
                'response': "Hello! Welcome to Digital Mentorship Platform. How can I assist you today?",
                'confidence': 0.9
            },
            {
                'keywords': ['thank', 'thanks', 'appreciate'],
                'response': "You're welcome! Is there anything else I can help you with?",
                'confidence': 0.9
            },
            {
                'keywords': ['password', 'reset password', 'forgot password'],
                'response': "To reset your password, click 'Forgot Password' on the login page. You'll receive an email with reset instructions.",
                'confidence': 0.85
            },
            {
                'keywords': ['create account', 'sign up', 'register'],
                'response': "To create an account, visit our registration page and enter your details. You'll need a valid email address.",
                'confidence': 0.85
            },
            {
                'keywords': ['mentor', 'become mentor', 'apply mentor'],
                'response': "To become a mentor, complete your profile and apply through the mentorship section. Our team will review your experience.",
                'confidence': 0.85
            },
            {
                'keywords': ['mentee', 'find mentor', 'need mentor'],
                'response': "As a mentee, you'll be matched with suitable mentors based on your goals and interests. Complete your profile to get started.",
                'confidence': 0.85
            },
            {
                'keywords': ['contact', 'support', 'help', 'email'],
                'response': "For support, email support@digital-mentorship.com or use the contact form on our website.",
                'confidence': 0.85
            },
            {
                'keywords': ['feature', 'what can', 'platform do'],
                'response': "Our platform offers mentorship matching, progress tracking, video calls, chat, and resource sharing between mentors and mentees.",
                'confidence': 0.8
            },
        ]
        
        # Check each rule
        for rule in rules:
            for keyword in rule['keywords']:
                if keyword in user_query_lower:
                    return {
                        'answer': rule['response'],
                        'confidence': rule['confidence']
                    }
        
        return None
    
    def _template_response(self, user_query: str) -> str:
        """Generate template-based response"""
        
        # Categorize the query
        if any(word in user_query.lower() for word in ['how', 'what', 'when', 'where', 'why', 'can']):
            # Question-type query
            templates = [
                "Based on your question about '{topic}', here's what I can tell you: Our platform helps with mentorship connections. For specific details, please provide more context or your email for personalized assistance.",
                
                "Regarding '{topic}', our mentorship platform offers various features. Could you provide more details about what you're looking for?",
                
                "I understand you're asking about '{topic}'. The best way to assist you is to have our team review your specific case. Could you share your email address?"
            ]
        else:
            # Statement-type query
            templates = [
                "Thank you for sharing about '{topic}'. Our mentorship platform can help with that. For personalized assistance, could you provide your email?",
                
                "I see you mentioned '{topic}'. Our team can provide detailed guidance on this. Would you like to share your email for follow-up?",
                
                "Regarding '{topic}', we have resources available. To connect you with the right information, could you please provide your email address?"
            ]
        
        # Extract main topic (first few words)
        topic = ' '.join(user_query.split()[:5])
        
        # Select random template
        template = random.choice(templates)
        response = template.format(topic=topic)
        
        return response
    
    def _fallback_response(self, user_query: str) -> Dict:
        """Fallback response"""
        fallbacks = [
            "I understand you need assistance with mentorship. For detailed help, could you please provide your email address so our team can contact you?",
            "Thank you for reaching out. To ensure you get accurate information, please share your email address for follow-up.",
            "I want to provide you with the best assistance. Could you please provide your email address so we can help you properly?"
        ]
        
        return {
            'response': random.choice(fallbacks),
            'confidence': 0.3,
            'faq_id': None,
            'source': 'fallback',
            'response_time': 0.1
        }


class FreeAssistanceManager:
    """FREE Assistance Manager - no API costs!"""
    
    def __init__(self):
        self.ai_service = FreeAIService()
        print("✅ FREE Assistance Manager initialized - No API costs!")
    
    def create_chat_session(self, request, email=None):
        """Create new assistance session"""
        import uuid
        
        session_id = f"free_{uuid.uuid4().hex[:8]}"
        
        chat_session = AssistanceChat.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id,
            email=email,
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            status='ai_handled'
        )
        
        print(f"✅ New FREE session created: {session_id}")
        return chat_session
    
    def process_question(self, chat_session, question):
        """Process user question"""
        try:
            # Save user question
            AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='user_question',
                content=question,
                sender=chat_session.user
            )
            
            # Get chat history
            chat_history = list(chat_session.messages.values(
                'message_type', 'content'
            ).order_by('created_at'))
            
            # Get AI response
            ai_result = self.ai_service.generate_response(question, chat_history)
            
            # Check if email is needed
            if ai_result['confidence'] < 0.5 and not chat_session.email:
                chat_session.status = 'human_requested'
                chat_session.save()
                
                # Add system message
                AssistanceMessage.objects.create(
                    chat=chat_session,
                    message_type='system',
                    content="System: Requested user email for better assistance."
                )
                
                return {
                    'response': ai_result['response'],
                    'requires_email': True,
                    'confidence': ai_result['confidence']
                }
            
            # Save AI response
            AssistanceMessage.objects.create(
                chat=chat_session,
                message_type='ai_response',
                content=ai_result['response'],
                ai_model='free-local-model',
                ai_response_quality=int(ai_result['confidence'] * 100)
            )
            
            # Log response
            AIResponseLog.objects.create(
                chat=chat_session,
                user_query=question,
                ai_response=ai_result['response'],
                model_used='free-local',
                confidence_score=ai_result['confidence'],
                response_time=ai_result.get('response_time', 1.0)
            )
            
            return {
                'response': ai_result['response'],
                'requires_email': False,
                'confidence': ai_result['confidence'],
                'faq_id': ai_result.get('faq_id'),
                'source': ai_result.get('source', 'free-ai')
            }
            
        except Exception as e:
            print(f"❌ Error processing question: {e}")
            return {
                'response': "Please provide your email address for detailed assistance from our team.",
                'requires_email': True,
                'confidence': 0.1
            }
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0]
        return request.META.get('REMOTE_ADDR')